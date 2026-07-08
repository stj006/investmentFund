"""智能定投：A 股核心按估值分位；QDII 海外层固定日定投。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.valuation import fetch_index_pe_snapshot


@dataclass
class SmartDcaHint:
    fund_code: str | None
    index_code: str
    index_name: str
    pe_ttm: float | None
    pe_percentile: float | None
    base_daily_cny: float
    suggested_daily_cny: float
    multiplier: float
    action: str  # normal | double | half | pause | fixed
    hint: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SmartDcaPlan:
    core_guidance: SmartDcaHint | None
    dca_funds: list[SmartDcaHint]

    def to_dict(self) -> dict:
        return {
            "core_guidance": self.core_guidance.to_dict() if self.core_guidance else None,
            "dca_funds": [f.to_dict() for f in self.dca_funds],
        }


def _eval_core_guidance(cfg: dict) -> SmartDcaHint:
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
            fund_code=None,
            index_code=index_code,
            index_name=index_name,
            pe_ttm=snap.pe_ttm,
            pe_percentile=None,
            base_daily_cny=base,
            suggested_daily_cny=base,
            multiplier=1.0,
            action="normal",
            hint="A 股指数估值暂不可用；宽基加仓可参考基础金额，QDII 见下方固定定投",
        )

    pe = snap.pe_percentile
    if pe >= very_high_pct:
        mul, action = very_high_mul, "pause"
        hint = (
            f"{index_name} PE 分位 {pe*100:.0f}% ≥ {very_high_pct*100:.0f}%，"
            f"建议暂停或减少宽基一次性加仓；卫星可分批止盈"
        )
    elif pe >= high_pct:
        mul, action = high_mul, "half"
        hint = (
            f"{index_name} PE 分位 {pe*100:.0f}% ≥ {high_pct*100:.0f}%，"
            f"宽基加仓建议减半"
        )
    elif pe <= low_pct:
        mul, action = low_mul, "double"
        hint = (
            f"{index_name} PE 分位 {pe*100:.0f}% ≤ {low_pct*100:.0f}%，"
            f"宽基加仓/定投可加倍"
        )
    else:
        mul, action = 1.0, "normal"
        hint = f"{index_name} PE 分位 {pe*100:.0f}% 处于合理区间，宽基按基础金额"

    return SmartDcaHint(
        fund_code=None,
        index_code=index_code,
        index_name=index_name,
        pe_ttm=snap.pe_ttm,
        pe_percentile=round(pe * 100, 1),
        base_daily_cny=base,
        suggested_daily_cny=round(base * mul, 2),
        multiplier=mul,
        action=action,
        hint=hint,
    )


def evaluate_smart_dca(strategy: dict) -> SmartDcaPlan | None:
    cfg = strategy.get("smart_dca") or {}
    if not cfg.get("enabled", False):
        return None

    core = _eval_core_guidance(cfg)
    dca_funds: list[SmartDcaHint] = []
    base = float(cfg.get("base_daily_cny", 10))
    hedge_codes = [str(c).zfill(6) for c in (cfg.get("hedge_fund_codes") or ["270042"])]
    hedge_fixed = bool(cfg.get("hedge_fixed_amount", True))

    for code in hedge_codes:
        if hedge_fixed:
            dca_funds.append(
                SmartDcaHint(
                    fund_code=code,
                    index_code="—",
                    index_name="海外 QDII",
                    pe_ttm=None,
                    pe_percentile=None,
                    base_daily_cny=base,
                    suggested_daily_cny=base,
                    multiplier=1.0,
                    action="fixed",
                    hint=f"{code} 纳指 QDII 固定 {base:.0f} 元/天，不随 A 股 PE 分位调整",
                )
            )
        else:
            dca_funds.append(core)

    return SmartDcaPlan(core_guidance=core, dca_funds=dca_funds)
