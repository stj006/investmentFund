"""智能定投：基于指数估值分位动态调整定投倍数。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.valuation import fetch_index_pe_snapshot


@dataclass
class SmartDcaHint:
    index_code: str
    index_name: str
    pe_ttm: float | None
    pe_percentile: float | None
    base_daily_cny: float
    suggested_daily_cny: float
    multiplier: float
    action: str  # normal | double | half | pause
    hint: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_smart_dca(strategy: dict) -> SmartDcaHint | None:
    cfg = strategy.get("smart_dca") or {}
    if not cfg.get("enabled", False):
        return None

    index_code = str(cfg.get("index_code", "000300.SH"))
    index_name = "沪深300" if "000300" in index_code else index_code
    base = float(cfg.get("base_daily_cny", 10))
    low_pct = float(cfg.get("low_percentile", 0.30))
    high_pct = float(cfg.get("high_percentile", 0.70))
    very_high_pct = float(cfg.get("very_high_percentile", 0.90))
    low_mul = float(cfg.get("low_multiplier", 2.0))
    high_mul = float(cfg.get("high_multiplier", 0.5))
    very_high_mul = float(cfg.get("very_high_multiplier", 0.0))

    snap = fetch_index_pe_snapshot(index_code)
    if snap.pe_percentile is None:
        return SmartDcaHint(
            index_code=index_code,
            index_name=index_name,
            pe_ttm=snap.pe_ttm,
            pe_percentile=None,
            base_daily_cny=base,
            suggested_daily_cny=base,
            multiplier=1.0,
            action="normal",
            hint="指数估值暂不可用，维持基础定投金额",
        )

    pe = snap.pe_percentile
    if pe >= very_high_pct:
        mul, action = very_high_mul, "pause"
        hint = f"{index_name} PE 分位 {pe*100:.0f}% ≥ {very_high_pct*100:.0f}%，建议暂停或大幅减量定投"
    elif pe >= high_pct:
        mul, action = high_mul, "half"
        hint = f"{index_name} PE 分位 {pe*100:.0f}% ≥ {high_pct*100:.0f}%，建议定投减半"
    elif pe <= low_pct:
        mul, action = low_mul, "double"
        hint = f"{index_name} PE 分位 {pe*100:.0f}% ≤ {low_pct*100:.0f}%，建议加倍定投"
    else:
        mul, action = 1.0, "normal"
        hint = f"{index_name} PE 分位 {pe*100:.0f}% 处于合理区间，维持基础定投"

    suggested = round(base * mul, 2)
    return SmartDcaHint(
        index_code=index_code,
        index_name=index_name,
        pe_ttm=snap.pe_ttm,
        pe_percentile=round(pe * 100, 1),
        base_daily_cny=base,
        suggested_daily_cny=suggested,
        multiplier=mul,
        action=action,
        hint=hint,
    )
