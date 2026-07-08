"""硬规则扫描：优先于 AI，触发结果写入建议上下文。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

from src.analytics.core_satellite import build_role_map, evaluate_core_satellite
from src.analytics.trailing_stop import check_trailing_stop
from src.analytics.valuation import check_valuation_take_profit
from src.analytics.portfolio import PortfolioSummary
from src.risk.rebalance_state import mark_rebalance_signaled, should_signal_rebalance
from src.risk.take_profit_state import mark_step_signaled, next_step_to_signal


@dataclass
class RuleSignal:
    rule_id: str
    severity: str  # info | warning | critical
    fund_code: str | None
    message: str
    suggested_action: str  # hold | add | reduce | switch

    def to_dict(self) -> dict:
        return asdict(self)


def _days_since(date_str: str) -> int | None:
    try:
        d = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        return (date.today() - d).days
    except ValueError:
        return None


def evaluate_rules(
    portfolio: PortfolioSummary,
    strategy: dict,
    positions_cfg: list[dict[str, str]],
    theme_by_code: dict[str, str],
    fund_universe: list[dict[str, str]] | None = None,
) -> list[RuleSignal]:
    signals: list[RuleSignal] = []
    alloc = strategy.get("allocation", {})
    sig = strategy.get("signals", {})
    trading = strategy.get("trading", {})
    cs_cfg = strategy.get("core_satellite") or {}
    role_by_code = build_role_map(fund_universe or [])

    max_single = float(alloc.get("max_single_fund_ratio", 0.2)) * 100
    max_theme = float(alloc.get("max_theme_ratio", 0.4)) * 100
    relax_below = float(alloc.get("relax_caps_when_value_below", 0))
    stop_loss = float(sig.get("stop_loss_ratio", -0.15)) * 100
    stop_loss_enabled = bool(sig.get("stop_loss_enabled", True))
    take_profit = float(sig.get("take_profit_ratio", 0.30)) * 100
    min_switch_days = int(trading.get("min_days_between_switch", 30))

    caps_relaxed = relax_below > 0 and portfolio.total_market_value < relax_below
    if caps_relaxed:
        signals.append(
            RuleSignal(
                rule_id="SMALL_ACCOUNT_MODE",
                severity="info",
                fund_code=None,
                message=(
                    f"账户市值 {portfolio.total_market_value:.2f} 元 "
                    f"低于 {relax_below:.0f} 元，暂不检查单基/主题仓位上限"
                ),
                suggested_action="hold",
            )
        )

    if not caps_relaxed:
        for p in portfolio.positions:
            if p.weight_pct > max_single:
                signals.append(
                    RuleSignal(
                        rule_id="POSITION_CAP",
                        severity="warning",
                        fund_code=p.fund_code,
                        message=f"{p.fund_name} 仓位 {p.weight_pct:.1f}% 超过上限 {max_single:.0f}%",
                        suggested_action="reduce",
                    )
                )

        theme_weight: dict[str, float] = {}
        for p in portfolio.positions:
            theme = theme_by_code.get(p.fund_code, "未分类")
            theme_weight[theme] = theme_weight.get(theme, 0) + p.weight_pct
        for theme, w in theme_weight.items():
            if w > max_theme:
                signals.append(
                    RuleSignal(
                        rule_id="THEME_CAP",
                        severity="warning",
                        fund_code=None,
                        message=f"主题「{theme}」合计仓位 {w:.1f}% 超过上限 {max_theme:.0f}%",
                        suggested_action="reduce",
                    )
                )

        if cs_cfg.get("enabled"):
            sat_target = float(cs_cfg.get("satellite_target_ratio", 0.20)) * 100
            sat_threshold = float(cs_cfg.get("rebalance_threshold", 0.05)) * 100
            sat_weight = sum(
                p.weight_pct
                for p in portfolio.positions
                if role_by_code.get(p.fund_code) == "satellite"
            )
            if sat_weight > sat_target + sat_threshold:
                signals.append(
                    RuleSignal(
                        rule_id="SATELLITE_CAP",
                        severity="warning",
                        fund_code=None,
                        message=(
                            f"行业卫星合计 {sat_weight:.1f}% 超过目标 {sat_target:.0f}%"
                            f"（+{sat_threshold:.0f}% 容忍），建议减卫星、增宽基"
                        ),
                        suggested_action="reduce",
                    )
                )

    steps = sig.get("take_profit_steps", [])
    sell_ratio = float(sig.get("take_profit_sell_ratio", 0.33))
    sorted_steps = sorted(float(s) for s in steps) if steps else []

    for p in portfolio.positions:
        if stop_loss_enabled and p.unrealized_pnl_pct <= stop_loss:
            signals.append(
                RuleSignal(
                    rule_id="STOP_LOSS",
                    severity="critical",
                    fund_code=p.fund_code,
                    message=f"{p.fund_name} 浮亏 {p.unrealized_pnl_pct:.2f}% 触及止损线 {stop_loss:.0f}%",
                    suggested_action="reduce",
                )
            )
        elif p.unrealized_pnl_pct >= take_profit:
            signals.append(
                RuleSignal(
                    rule_id="TAKE_PROFIT",
                    severity="info",
                    fund_code=p.fund_code,
                    message=f"{p.fund_name} 浮盈 {p.unrealized_pnl_pct:.2f}% 达到止盈观察线 {take_profit:.0f}%",
                    suggested_action="reduce",
                )
            )

        if sorted_steps and p.unrealized_pnl_pct > 0:
            pnl_ratio = p.unrealized_pnl_pct / 100.0
            step_i = next_step_to_signal(p.fund_code, pnl_ratio, sorted_steps)
            if step_i is not None:
                step_pct = sorted_steps[step_i] * 100
                signals.append(
                    RuleSignal(
                        rule_id="TAKE_PROFIT_STEP",
                        severity="info",
                        fund_code=p.fund_code,
                        message=(
                            f"{p.fund_name} 浮盈 {p.unrealized_pnl_pct:.2f}% 首次达到分批止盈第 {step_i + 1} 档"
                            f"（{step_pct:.0f}%），建议卖出 {sell_ratio*100:.0f}% 仓位"
                        ),
                        suggested_action="reduce",
                    )
                )
                mark_step_signaled(p.fund_code, step_i)

    for p in portfolio.positions:
        ts = check_trailing_stop(
            p.fund_code, p.fund_name, p.unit_nav, p.unrealized_pnl_pct, strategy
        )
        if ts and ts.triggered:
            signals.append(
                RuleSignal(
                    rule_id="TRAILING_STOP",
                    severity="warning",
                    fund_code=p.fund_code,
                    message=(
                        f"{p.fund_name} 浮盈 {ts.profit_pct:.2f}%，"
                        f"自最高净值 {ts.peak_nav:.4f} 回撤 {abs(ts.drawdown_pct):.1f}%，"
                        f"建议止盈锁定利润"
                    ),
                    suggested_action="reduce",
                )
            )

    val_sig = check_valuation_take_profit(strategy)
    if val_sig and val_sig.triggered:
        severity = "warning"
        if "极高" in val_sig.hint:
            severity = "critical"
        signals.append(
            RuleSignal(
                rule_id="VALUATION_STOP",
                severity=severity,
                fund_code=None,
                message=val_sig.hint,
                suggested_action="reduce",
            )
        )

    cs = evaluate_core_satellite(portfolio, strategy, role_by_code=role_by_code)
    interval_days = int(cs_cfg.get("rebalance_interval_days", 180))
    if cs and cs.needs_rebalance and should_signal_rebalance(interval_days):
        for hint in cs.hints:
            if "暂不计为偏离" in hint:
                signals.append(
                    RuleSignal(
                        rule_id="HEDGE_DCA_BUILD",
                        severity="info",
                        fund_code=None,
                        message=hint,
                        suggested_action="hold",
                    )
                )
            else:
                signals.append(
                    RuleSignal(
                        rule_id="REBALANCE",
                        severity="info",
                        fund_code=None,
                        message=hint,
                        suggested_action="reduce",
                    )
                )
        mark_rebalance_signaled()

    for pos in positions_cfg:
        buy_date = pos.get("first_buy_date") or pos.get("last_buy_date", "")
        days = _days_since(buy_date)
        if days is not None and days < 7:
            signals.append(
                RuleSignal(
                    rule_id="REDEMPTION_FEE_7D",
                    severity="warning",
                    fund_code=pos["fund_code"],
                    message=f"{pos.get('fund_name', pos['fund_code'])} 距首次买入仅 {days} 天，赎回可能收取惩罚性费用",
                    suggested_action="hold",
                )
            )

    for pos in positions_cfg:
        days = _days_since(pos.get("last_buy_date", ""))
        if days is not None and days < min_switch_days:
            signals.append(
                RuleSignal(
                    rule_id="SWITCH_COOLDOWN",
                    severity="info",
                    fund_code=pos["fund_code"],
                    message=f"距上次买入 {days} 天，策略建议换基间隔不少于 {min_switch_days} 天",
                    suggested_action="hold",
                )
            )

    return signals


def enforce_critical_rules(
    advice: dict,
    rule_signals: list[RuleSignal],
    whitelist: set[str],
    strategy: dict | None = None,
    portfolio: PortfolioSummary | None = None,
) -> dict:
    """critical 规则若 AI 未给出减仓，注入保底建议。"""
    actions = list(advice.get("actions") or [])
    existing = {(a.get("fund_code"), a.get("action")) for a in actions}
    strategy = strategy or {}
    held = {p.fund_code for p in portfolio.positions} if portfolio else set()
    satellite_codes = {
        str(c).zfill(6)
        for c in (strategy.get("core_satellite", {}).get("satellite_fund_codes") or [])
    }

    for sig in rule_signals:
        if sig.severity != "critical":
            continue

        targets: list[tuple[str, float, str]] = []
        if sig.fund_code:
            targets.append((sig.fund_code, 0.1, sig.message))
        elif sig.rule_id == "VALUATION_STOP" and satellite_codes:
            for code in satellite_codes:
                if code in whitelist and code in held:
                    targets.append(
                        (
                            code,
                            0.25,
                            f"[规则保底] 市场估值极高，建议卫星 {code} 减仓约 25%，利润转入宽基",
                        )
                    )

        for fund_code, ratio, reason in targets:
            key = (fund_code, "reduce")
            if key in existing or fund_code not in whitelist:
                continue
            actions.append(
                {
                    "fund_code": fund_code,
                    "action": "reduce",
                    "ratio": ratio,
                    "reason": reason,
                    "confidence": 1.0,
                    "rule_hits": [sig.rule_id],
                    "requires_human_confirm": True,
                }
            )
            existing.add(key)

    advice["actions"] = actions
    return advice
