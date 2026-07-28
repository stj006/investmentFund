"""核心-卫星资产配置：宽基/行业占比（定投层不参与再平衡）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.fund_roles import is_broad_index
from src.analytics.portfolio import PortfolioSummary
from src.analytics.satellite_sleeve import evaluate_satellite_sleeve


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
    managed_market_value: float
    excluded_market_value: float
    exclude_hedge_from_allocation: bool
    rebalance_threshold_pct: float
    needs_rebalance: bool
    hints: list[str]
    satellite_sleeve: dict | None = None

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


def excluded_allocation_codes(strategy: dict) -> set[str]:
    """定投/旁路仓：不参与 60/40 再平衡。"""
    cfg = strategy.get("core_satellite") or {}
    trading = strategy.get("trading") or {}
    codes: set[str] = set()
    for c in cfg.get("hedge_fund_codes") or []:
        codes.add(str(c).zfill(6))
    for c in cfg.get("exclude_from_allocation_codes") or []:
        codes.add(str(c).zfill(6))
    for c in trading.get("dca_only_funds") or []:
        codes.add(str(c).zfill(6))
    return codes


def _role_for_position(
    fund_code: str,
    fund_name: str,
    cfg: dict,
    broad_kw: list[str],
    role_by_code: dict[str, str],
    excluded: set[str],
) -> str:
    code = str(fund_code).zfill(6)
    if code in excluded:
        return "hedge"

    mapped = role_by_code.get(code)
    if mapped in ("core", "core_growth", "satellite", "hedge"):
        return mapped

    growth_codes = {str(c).zfill(6) for c in (cfg.get("core_growth_fund_codes") or [])}
    core_codes = {str(c).zfill(6) for c in (cfg.get("core_fund_codes") or [])}
    satellite_codes = {str(c).zfill(6) for c in (cfg.get("satellite_fund_codes") or [])}
    if code in growth_codes:
        return "core_growth"
    if code in core_codes or is_broad_index(fund_name, broad_kw):
        return "core"
    if code in satellite_codes:
        return "satellite"
    return "satellite"


def evaluate_core_satellite(
    portfolio: PortfolioSummary,
    strategy: dict,
    *,
    role_by_code: dict[str, str] | None = None,
) -> CoreSatelliteSummary | None:
    cfg = strategy.get("core_satellite") or {}
    if not cfg.get("enabled", False):
        return None

    role_by_code = role_by_code or {}
    exclude_hedge = bool(cfg.get("exclude_hedge_from_allocation", True))
    excluded = excluded_allocation_codes(strategy) if exclude_hedge else set()

    broad_kw = cfg.get("broad_index_keywords") or [
        "沪深300",
        "中证A500",
        "A500",
        "上证50",
        "红利",
    ]
    core_target = float(cfg.get("core_target_ratio", 0.60)) * 100
    satellite_target = float(cfg.get("satellite_target_ratio", 0.40)) * 100
    hedge_target = float(cfg.get("hedge_target_ratio", 0.0)) * 100
    growth_max = float(cfg.get("core_growth_max_ratio", 0.10)) * 100
    threshold = float(cfg.get("rebalance_threshold", 0.05)) * 100

    value_by_role = {
        "core": 0.0,
        "core_growth": 0.0,
        "satellite": 0.0,
        "hedge": 0.0,
        "other": 0.0,
    }
    satellite_positions = []
    for p in portfolio.positions:
        role = _role_for_position(
            p.fund_code, p.fund_name, cfg, broad_kw, role_by_code, excluded
        )
        bucket = role if role in value_by_role else "other"
        value_by_role[bucket] += p.market_value
        if role == "satellite":
            satellite_positions.append(p)

    excluded_value = value_by_role["hedge"]
    managed_value = (
        value_by_role["core"]
        + value_by_role["core_growth"]
        + value_by_role["satellite"]
        + value_by_role["other"]
    )
    denom = managed_value if managed_value > 0 else 1.0

    role_weight = {
        k: (v / denom * 100.0)
        for k, v in value_by_role.items()
        if k != "hedge"
    }
    role_weight["hedge"] = 0.0
    core_total = role_weight.get("core", 0.0) + role_weight.get("core_growth", 0.0)
    sat_pct = role_weight.get("satellite", 0.0)
    growth_pct = role_weight.get("core_growth", 0.0)
    other_pct = role_weight.get("other", 0.0)

    hints: list[str] = []
    needs = False

    if exclude_hedge:
        if excluded_value > 0:
            hints.append(
                f"定投/旁路仓（纳指等）市值约 {excluded_value:.0f} 元，"
                f"不计入 60/40 再平衡，系统不关注其涨跌"
            )
        elif excluded:
            hints.append("定投/旁路仓（如 270042）不计入 60/40 再平衡")

    if growth_pct > growth_max + threshold:
        needs = True
        hints.append(
            f"成长增强（500信息等）占「管理仓」 {growth_pct:.1f}% 超过上限 {growth_max:.0f}%，"
            f"建议减至 {growth_max:.0f}% 以内，增量优先买沪深300/A500"
        )

    checks = [
        ("core_total", core_total, core_target, "宽基核心（含真宽基+成长增强）"),
        ("satellite", sat_pct, satellite_target, "行业卫星合计"),
    ]
    for layer, actual, target, label in checks:
        drift = actual - target
        if abs(drift) <= threshold:
            continue
        needs = True
        if drift > 0:
            action = (
                "建议减卫星、利润转入真宽基（110020/022430）"
                if layer == "satellite"
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

    if other_pct > 1:
        needs = True
        hints.append(f"未分类仓位 {other_pct:.1f}%，请在 fund_universe.role 中归类")

    sleeve_summary = evaluate_satellite_sleeve(
        portfolio,
        strategy,
        satellite_positions=satellite_positions,
        managed_value=managed_value,
    )
    sleeve_dict = None
    if sleeve_summary:
        sleeve_dict = sleeve_summary.to_dict()
        hints.extend(sleeve_summary.hints)
        if sleeve_summary.needs_adjust:
            needs = True

    if not needs and managed_value > 0:
        hints.append(
            f"60/40 结构正常（相对管理仓）：宽基 {core_total:.1f}% / 行业 {sat_pct:.1f}%"
            + (f"；定投旁路约 {excluded_value:.0f} 元已排除" if excluded_value > 0 else "")
        )

    return CoreSatelliteSummary(
        core_target_pct=core_target,
        satellite_target_pct=satellite_target,
        hedge_target_pct=hedge_target,
        core_actual_pct=round(core_total, 2),
        core_broad_actual_pct=round(role_weight.get("core", 0.0), 2),
        core_growth_actual_pct=round(growth_pct, 2),
        satellite_actual_pct=round(sat_pct, 2),
        hedge_actual_pct=0.0,
        unclassified_pct=round(other_pct, 2),
        managed_market_value=round(managed_value, 2),
        excluded_market_value=round(excluded_value, 2),
        exclude_hedge_from_allocation=exclude_hedge,
        rebalance_threshold_pct=threshold,
        needs_rebalance=needs,
        hints=hints,
        satellite_sleeve=sleeve_dict,
    )
