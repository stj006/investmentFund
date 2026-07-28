"""卫星补仓：主卫星阶梯补（DIP_BUY_SATELLITE）+ 次席结构性补缺。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.core_satellite import evaluate_core_satellite
from src.analytics.portfolio import PortfolioSummary
from src.analytics.satellite_logic_exit import evaluate_satellite_logic_exits
from src.analytics.trailing_stop import _nav_history


@dataclass
class SatelliteDipHint:
    rule_kind: str  # primary_dip | secondary_structure | skip
    triggered: bool
    fund_code: str | None
    fund_name: str | None
    drawdown_from_peak_pct: float | None
    managed_pct: float | None
    cap_pct: float | None
    step_label: str | None
    suggested_cny: float
    action: str  # add | hold | skip
    hint: str

    def to_dict(self) -> dict:
        return asdict(self)


def _peak_drawdown_pct(fund_code: str, lookback: int, current_nav: float) -> float | None:
    points = _nav_history(fund_code, lookback)
    if len(points) < 5:
        return None
    navs = [p["nav"] for p in points]
    peak = max(navs)
    if peak <= 0:
        return None
    last = current_nav if current_nav > 0 else navs[-1]
    return (last - peak) / peak * 100.0


def evaluate_dip_buy_satellite(
    portfolio: PortfolioSummary,
    strategy: dict,
    *,
    role_by_code: dict[str, str] | None = None,
    theme_by_code: dict[str, str] | None = None,
) -> list[SatelliteDipHint]:
    cfg = strategy.get("dip_buy_satellite") or {}
    if not cfg.get("enabled", False):
        return []

    sleeve = strategy.get("satellite_sleeve") or {}
    primary_code = str(
        cfg.get("primary_fund") or sleeve.get("primary_preferred") or "012737"
    ).zfill(6)
    secondary_code = str(
        cfg.get("secondary_fund") or sleeve.get("secondary_preferred") or "004253"
    ).zfill(6)
    primary_cap = float(cfg.get("primary_max_managed_ratio", sleeve.get("primary_ratio", 0.25))) * 100
    secondary_target = float(
        cfg.get("secondary_target_ratio", sleeve.get("secondary_ratio", 0.15))
    ) * 100
    secondary_gap = float(cfg.get("secondary_gap_threshold", 0.05)) * 100
    lookback = int(cfg.get("lookback_days", 90))
    budget = float(cfg.get("reserve_budget_cny", 1000))
    block_on_logic_exit = bool(cfg.get("block_when_logic_exit_reduce", True))
    steps = cfg.get("steps") or [
        {"drawdown_pct": 0.12, "reserve_ratio": 0.20},
        {"drawdown_pct": 0.20, "reserve_ratio": 0.30},
        {"drawdown_pct": 0.28, "reserve_ratio": 0.40},
    ]
    sorted_steps = sorted(
        (
            {
                "drawdown_pct": float(s.get("drawdown_pct", 0)),
                "reserve_ratio": float(s.get("reserve_ratio", 0)),
            }
            for s in steps
        ),
        key=lambda x: x["drawdown_pct"],
    )

    cs = evaluate_core_satellite(portfolio, strategy, role_by_code=role_by_code or {})
    managed = cs.managed_market_value if cs and cs.managed_market_value > 0 else portfolio.total_market_value
    if managed <= 0:
        managed = 1.0

    by_code = {str(p.fund_code).zfill(6): p for p in portfolio.positions}
    hints: list[SatelliteDipHint] = []

    # --- 次席结构性补缺（黄金等）：不到目标才补，不做下跌加倍 ---
    if cfg.get("secondary_structure_topup", True):
        sec = by_code.get(secondary_code)
        sec_pct = (sec.market_value / managed * 100.0) if sec else 0.0
        if sec_pct < secondary_target - secondary_gap:
            need_pct = secondary_target - sec_pct
            suggest = round(managed * need_pct / 100.0, 2)
            suggest = min(suggest, float(cfg.get("secondary_max_topup_cny", 1500)))
            name = sec.fund_name if sec else secondary_code
            hints.append(
                SatelliteDipHint(
                    rule_kind="secondary_structure",
                    triggered=True,
                    fund_code=secondary_code,
                    fund_name=name,
                    drawdown_from_peak_pct=None,
                    managed_pct=round(sec_pct, 2),
                    cap_pct=secondary_target,
                    step_label="结构补缺",
                    suggested_cny=suggest,
                    action="add",
                    hint=(
                        f"次席 {secondary_code} 占管理仓 {sec_pct:.1f}% "
                        f"低于目标 {secondary_target:.0f}%："
                        f"建议结构性补约 {suggest:.0f} 元（按仓位目标，非下跌加倍）"
                    ),
                )
            )

    # --- 主卫星阶梯补仓 ---
    primary = by_code.get(primary_code)
    if not primary:
        hints.append(
            SatelliteDipHint(
                rule_kind="primary_dip",
                triggered=False,
                fund_code=primary_code,
                fund_name=None,
                drawdown_from_peak_pct=None,
                managed_pct=0.0,
                cap_pct=primary_cap,
                step_label=None,
                suggested_cny=0.0,
                action="skip",
                hint=f"主卫星 {primary_code} 未持仓，阶梯补仓不适用；新建仓请另按计划小额定投",
            )
        )
        return hints

    primary_pct = primary.market_value / managed * 100.0
    if primary_pct >= primary_cap - 0.5:
        hints.append(
            SatelliteDipHint(
                rule_kind="primary_dip",
                triggered=False,
                fund_code=primary.fund_code,
                fund_name=primary.fund_name,
                drawdown_from_peak_pct=None,
                managed_pct=round(primary_pct, 2),
                cap_pct=primary_cap,
                step_label=None,
                suggested_cny=0.0,
                action="skip",
                hint=(
                    f"主卫星 {primary.fund_code} 已占管理仓 {primary_pct:.1f}% "
                    f"接近/达到上限 {primary_cap:.0f}%，禁止下跌补仓；应减仓或持有"
                ),
            )
        )
        return hints

    if block_on_logic_exit:
        exits = evaluate_satellite_logic_exits(
            portfolio,
            strategy,
            role_by_code=role_by_code,
            theme_by_code=theme_by_code,
        )
        for ex in exits:
            if str(ex.fund_code).zfill(6) == primary_code and ex.level in (
                "reduce",
                "deep_reduce",
            ):
                hints.append(
                    SatelliteDipHint(
                        rule_kind="primary_dip",
                        triggered=False,
                        fund_code=primary.fund_code,
                        fund_name=primary.fund_name,
                        drawdown_from_peak_pct=None,
                        managed_pct=round(primary_pct, 2),
                        cap_pct=primary_cap,
                        step_label=None,
                        suggested_cny=0.0,
                        action="skip",
                        hint=(
                            f"主卫星 {primary.fund_code} 已触发逻辑退出减仓档，"
                            f"禁止补仓；先复盘逻辑，优先减仓回宽基"
                        ),
                    )
                )
                return hints

    dd_peak = _peak_drawdown_pct(primary_code, lookback, primary.unit_nav)
    # 取「自高点回撤」与「浮亏」中更严重者作为触发幅度（均为负向）
    loss_proxy = primary.unrealized_pnl_pct
    severity = loss_proxy
    if dd_peak is not None:
        severity = min(loss_proxy, dd_peak)

    matched = None
    for step in sorted_steps:
        if abs(severity) + 1e-9 >= step["drawdown_pct"] * 100:
            matched = step

    if matched is None:
        first = sorted_steps[0]["drawdown_pct"] * 100
        hints.append(
            SatelliteDipHint(
                rule_kind="primary_dip",
                triggered=False,
                fund_code=primary.fund_code,
                fund_name=primary.fund_name,
                drawdown_from_peak_pct=round(dd_peak, 2) if dd_peak is not None else None,
                managed_pct=round(primary_pct, 2),
                cap_pct=primary_cap,
                step_label=None,
                suggested_cny=0.0,
                action="hold",
                hint=(
                    f"主卫星 {primary.fund_code} 回撤/浮亏约 {severity:.1f}% "
                    f"未达首档 {first:.0f}%，且仓位 {primary_pct:.1f}%<{primary_cap:.0f}%；"
                    f"暂不补，优先宽基或持有"
                ),
            )
        )
        return hints

    reserve_ratio = matched["reserve_ratio"]
    step_dd = matched["drawdown_pct"] * 100
    suggested = round(budget * reserve_ratio, 2)
    # 补完后不得明显突破主卫星上限
    room_cny = max(0.0, managed * (primary_cap - primary_pct) / 100.0)
    suggested = round(min(suggested, room_cny), 2)
    if suggested < 50:
        hints.append(
            SatelliteDipHint(
                rule_kind="primary_dip",
                triggered=False,
                fund_code=primary.fund_code,
                fund_name=primary.fund_name,
                drawdown_from_peak_pct=round(dd_peak, 2) if dd_peak is not None else None,
                managed_pct=round(primary_pct, 2),
                cap_pct=primary_cap,
                step_label=f"回撤≥{step_dd:.0f}%",
                suggested_cny=0.0,
                action="skip",
                hint=(
                    f"主卫星达补仓档但距上限 {primary_cap:.0f}% 空间不足 "
                    f"（当前 {primary_pct:.1f}%），不建议再补"
                ),
            )
        )
        return hints

    dd_txt = f"自高点回撤 {abs(dd_peak):.1f}%" if dd_peak is not None else "净值历史不足"
    hints.append(
        SatelliteDipHint(
            rule_kind="primary_dip",
            triggered=True,
            fund_code=primary.fund_code,
            fund_name=primary.fund_name,
            drawdown_from_peak_pct=round(dd_peak, 2) if dd_peak is not None else None,
            managed_pct=round(primary_pct, 2),
            cap_pct=primary_cap,
            step_label=f"回撤/浮亏≥{step_dd:.0f}%",
            suggested_cny=suggested,
            action="add",
            hint=(
                f"主卫星 {primary.fund_code} {primary.fund_name}：{dd_txt}，"
                f"浮亏 {primary.unrealized_pnl_pct:.1f}%（触发 {step_dd:.0f}% 档）；"
                f"占管理仓 {primary_pct:.1f}%<{primary_cap:.0f}%，"
                f"逻辑未触发减仓档时可小额补约 {suggested:.0f} 元；"
                f"补完仍须 ≤{primary_cap:.0f}%，多余资金优先宽基"
            ),
        )
    )
    return hints
