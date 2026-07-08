"""核心-卫星资产配置：计算实际占比与再平衡信号。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.fund_roles import is_broad_index
from src.analytics.portfolio import PortfolioSummary


@dataclass
class CoreSatelliteSummary:
    core_target_pct: float
    satellite_target_pct: float
    hedge_target_pct: float
    core_actual_pct: float
    core_broad_actual_pct: float
    core_growth_actual_pct: float
    satellite_actual_pct: float
    hedge_actual_pct: float
    unclassified_pct: float
    rebalance_threshold_pct: float
    needs_rebalance: bool
    hints: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def build_role_map(universe: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in universe:
        code = str(row.get("fund_code", "")).zfill(6)
        role = (row.get("role") or "").strip().lower()
        if code and role in ("core", "core_growth", "satellite", "hedge", "pool"):
            out[code] = role
    return out


def _role_for_position(
    fund_code: str,
    fund_name: str,
    cfg: dict,
    broad_kw: list[str],
    role_by_code: dict[str, str],
) -> str:
    code = str(fund_code).zfill(6)
    mapped = role_by_code.get(code)
    if mapped in ("core", "core_growth", "satellite", "hedge"):
        return mapped

    growth_codes = {str(c).zfill(6) for c in (cfg.get("core_growth_fund_codes") or [])}
    core_codes = {str(c).zfill(6) for c in (cfg.get("core_fund_codes") or [])}
    satellite_codes = {str(c).zfill(6) for c in (cfg.get("satellite_fund_codes") or [])}
    hedge_codes = {str(c).zfill(6) for c in (cfg.get("hedge_fund_codes") or [])}
    if code in growth_codes:
        return "core_growth"
    if code in core_codes or is_broad_index(fund_name, broad_kw):
        return "core"
    if code in hedge_codes:
        return "hedge"
    if code in satellite_codes:
        return "satellite"
    return "satellite"


def _hedge_building_via_dca(
    cfg: dict,
    trading: dict,
    portfolio: PortfolioSummary,
) -> bool:
    dca_only = {str(c).zfill(6) for c in (trading.get("dca_only_funds") or [])}
    hedge_codes = [str(c).zfill(6) for c in (cfg.get("hedge_fund_codes") or [])]
    if not hedge_codes:
        return False
    held = {p.fund_code for p in portfolio.positions}
    if held.intersection(hedge_codes):
        return False
    return all(c in dca_only for c in hedge_codes)


def evaluate_core_satellite(
    portfolio: PortfolioSummary,
    strategy: dict,
    *,
    role_by_code: dict[str, str] | None = None,
) -> CoreSatelliteSummary | None:
    cfg = strategy.get("core_satellite") or {}
    if not cfg.get("enabled", False):
        return None

    trading = strategy.get("trading") or {}
    role_by_code = role_by_code or {}
    broad_kw = cfg.get("broad_index_keywords") or [
        "沪深300",
        "中证A500",
        "A500",
        "上证50",
        "红利",
    ]
    core_target = float(cfg.get("core_target_ratio", 0.70)) * 100
    satellite_target = float(cfg.get("satellite_target_ratio", 0.20)) * 100
    hedge_target = float(cfg.get("hedge_target_ratio", 0.10)) * 100
    growth_max = float(cfg.get("core_growth_max_ratio", 0.10)) * 100
    threshold = float(cfg.get("rebalance_threshold", 0.05)) * 100
    hedge_dca_building = _hedge_building_via_dca(cfg, trading, portfolio)

    role_weight = {
        "core": 0.0,
        "core_growth": 0.0,
        "satellite": 0.0,
        "hedge": 0.0,
        "other": 0.0,
    }
    for p in portfolio.positions:
        role = _role_for_position(p.fund_code, p.fund_name, cfg, broad_kw, role_by_code)
        bucket = role if role in role_weight else "other"
        role_weight[bucket] += p.weight_pct

    core_total = role_weight["core"] + role_weight["core_growth"]
    hints: list[str] = []
    needs = False

    if role_weight["core_growth"] > growth_max + threshold:
        needs = True
        hints.append(
            f"成长增强（500信息等）实际 {role_weight['core_growth']:.1f}% 超过上限 {growth_max:.0f}%，"
            f"建议减至 {growth_max:.0f}% 以内，增量优先买沪深300/A500"
        )

    checks = [
        ("core_total", core_total, core_target, "宽基核心（含真宽基+成长增强）"),
        ("satellite", role_weight["satellite"], satellite_target, "行业卫星"),
        ("hedge", role_weight["hedge"], hedge_target, "防御/海外"),
    ]
    for layer, actual, target, label in checks:
        drift = actual - target
        if abs(drift) <= threshold:
            continue
        if layer == "hedge" and drift < 0 and hedge_dca_building:
            hints.append(
                f"{label} 目标 {target:.0f}%，当前通过纳指 QDII 日定投逐步建立（未计入持仓市值），暂不计为偏离"
            )
            continue
        needs = True
        if drift > 0:
            action = (
                "建议减卫星、利润转入沪深300（110020）与中证A500（022430）"
                if layer == "core_total" and role_weight["satellite"] > satellite_target
                else "建议减卫星、利润转入真宽基（110020/022430）"
                if layer != "core_total"
                else "建议减成长增强或卫星，增配沪深300/A500"
            )
            hints.append(
                f"{label} 实际 {actual:.1f}% 高于目标 {target:.0f}%（偏离 +{drift:.1f}%），{action}"
            )
        else:
            hints.append(
                f"{label} 实际 {actual:.1f}% 低于目标 {target:.0f}%（偏离 {drift:.1f}%），"
                f"建议优先买入 110020 沪深300 与 022430 中证A500"
            )

    if role_weight["other"] > 1:
        needs = True
        hints.append(f"未分类仓位 {role_weight['other']:.1f}%，请在 fund_universe.role 中归类")

    if not hints and portfolio.positions:
        hints.append(
            f"核心-卫星结构正常：真宽基 {role_weight['core']:.1f}% / "
            f"成长增强 {role_weight['core_growth']:.1f}% / "
            f"卫星 {role_weight['satellite']:.1f}% / 海外 {role_weight['hedge']:.1f}%"
        )

    return CoreSatelliteSummary(
        core_target_pct=core_target,
        satellite_target_pct=satellite_target,
        hedge_target_pct=hedge_target,
        core_actual_pct=round(core_total, 2),
        core_broad_actual_pct=round(role_weight["core"], 2),
        core_growth_actual_pct=round(role_weight["core_growth"], 2),
        satellite_actual_pct=round(role_weight["satellite"], 2),
        hedge_actual_pct=round(role_weight["hedge"], 2),
        unclassified_pct=round(role_weight["other"], 2),
        rebalance_threshold_pct=threshold,
        needs_rebalance=needs,
        hints=hints,
    )
