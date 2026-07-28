"""宽基阶梯补仓（DIP_BUY_CORE）：指数回撤 + 估值过滤。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.trend_observation import _index_series
from src.analytics.valuation import fetch_index_pe_snapshot


@dataclass
class DipBuyHint:
    triggered: bool
    index_code: str
    index_name: str
    drawdown_from_peak_pct: float | None
    pe_percentile: float | None
    step_label: str | None
    reserve_ratio: float
    suggested_cny: float
    target_funds: list[str]
    per_fund_cny: float
    action: str  # add | hold | skip
    hint: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_dip_buy_core(strategy: dict) -> DipBuyHint | None:
    cfg = strategy.get("dip_buy_core") or {}
    if not cfg.get("enabled", False):
        return None

    index_code = str(cfg.get("index_code") or strategy.get("benchmark", {}).get("index_code") or "000300.SH")
    index_name = "沪深300" if "000300" in index_code else index_code
    lookback = int(cfg.get("lookback_days", 120))
    max_pe = float(cfg.get("max_pe_percentile", 0.70))
    low_pe = float(cfg.get("low_pe_boost", 0.30))
    budget = float(cfg.get("reserve_budget_cny", 2000))
    targets = [str(c).zfill(6) for c in (cfg.get("target_funds") or ["110020", "022430"])]
    steps = cfg.get("steps") or [
        {"drawdown_pct": 0.10, "reserve_ratio": 0.20},
        {"drawdown_pct": 0.20, "reserve_ratio": 0.30},
        {"drawdown_pct": 0.30, "reserve_ratio": 0.50},
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

    points = _index_series(index_code, lookback)
    if len(points) < 10:
        return DipBuyHint(
            triggered=False,
            index_code=index_code,
            index_name=index_name,
            drawdown_from_peak_pct=None,
            pe_percentile=None,
            step_label=None,
            reserve_ratio=0.0,
            suggested_cny=0.0,
            target_funds=targets,
            per_fund_cny=0.0,
            action="skip",
            hint=f"{index_name} 指数历史不足，暂不给出宽基阶梯补仓提示",
        )

    closes = [p["nav"] for p in points]
    peak = max(closes)
    last = closes[-1]
    dd = (last - peak) / peak if peak > 0 else 0.0  # 负值
    dd_pct = round(dd * 100, 2)

    snap = fetch_index_pe_snapshot(index_code)
    pe = snap.pe_percentile  # 0-1 or None
    pe_display = round(pe * 100, 1) if pe is not None else None

    # 匹配最高已触发档位
    matched = None
    for step in sorted_steps:
        if abs(dd) + 1e-9 >= step["drawdown_pct"]:
            matched = step

    if matched is None:
        return DipBuyHint(
            triggered=False,
            index_code=index_code,
            index_name=index_name,
            drawdown_from_peak_pct=dd_pct,
            pe_percentile=pe_display,
            step_label=None,
            reserve_ratio=0.0,
            suggested_cny=0.0,
            target_funds=targets,
            per_fund_cny=0.0,
            action="hold",
            hint=(
                f"{index_name} 自近{lookback}日高点回撤 {abs(dd_pct):.1f}%，"
                f"未达首档补仓线（{sorted_steps[0]['drawdown_pct']*100:.0f}%），暂不阶梯补仓"
            ),
        )

    step_dd = matched["drawdown_pct"] * 100
    reserve_ratio = matched["reserve_ratio"]
    if pe is not None and pe <= low_pe:
        reserve_ratio = min(1.0, reserve_ratio * 1.25)

    if pe is not None and pe >= max_pe:
        return DipBuyHint(
            triggered=False,
            index_code=index_code,
            index_name=index_name,
            drawdown_from_peak_pct=dd_pct,
            pe_percentile=pe_display,
            step_label=f"回撤≥{step_dd:.0f}%",
            reserve_ratio=0.0,
            suggested_cny=0.0,
            target_funds=targets,
            per_fund_cny=0.0,
            action="skip",
            hint=(
                f"{index_name} 已回撤 {abs(dd_pct):.1f}%（达 {step_dd:.0f}% 档），"
                f"但 PE 分位 {pe_display}% ≥ {max_pe*100:.0f}%，估值偏高，"
                f"建议观望、不补仓；可继续持有宽基"
            ),
        )

    suggested = round(budget * reserve_ratio, 2)
    n = max(len(targets), 1)
    per = round(suggested / n, 2)
    pe_txt = f"，PE 分位 {pe_display}%" if pe_display is not None else ""
    funds_txt = " / ".join(targets)

    return DipBuyHint(
        triggered=True,
        index_code=index_code,
        index_name=index_name,
        drawdown_from_peak_pct=dd_pct,
        pe_percentile=pe_display,
        step_label=f"回撤≥{step_dd:.0f}%",
        reserve_ratio=reserve_ratio,
        suggested_cny=suggested,
        target_funds=targets,
        per_fund_cny=per,
        action="add",
        hint=(
            f"{index_name} 自近{lookback}日高点回撤 {abs(dd_pct):.1f}%（触发 {step_dd:.0f}% 档）{pe_txt}；"
            f"建议用备用金约 {suggested:.0f} 元阶梯补宽基（{funds_txt} 各约 {per:.0f} 元），"
            f"勿一次梭哈，保留后续更低档弹药"
        ),
    )
