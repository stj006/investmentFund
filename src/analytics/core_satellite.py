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
    satellite_actual_pct: float
    hedge_actual_pct: float
    unclassified_pct: float
    rebalance_threshold_pct: float
    needs_rebalance: bool
    hints: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _role_for_position(
    fund_code: str,
    fund_name: str,
    cfg: dict,
    broad_kw: list[str],
) -> str:
    core_codes = {str(c).zfill(6) for c in (cfg.get("core_fund_codes") or [])}
    satellite_codes = {str(c).zfill(6) for c in (cfg.get("satellite_fund_codes") or [])}
    hedge_codes = {str(c).zfill(6) for c in (cfg.get("hedge_fund_codes") or [])}
    code = str(fund_code).zfill(6)
    if code in core_codes or is_broad_index(fund_name, broad_kw):
        return "core"
    if code in hedge_codes:
        return "hedge"
    if code in satellite_codes:
        return "satellite"
    return "satellite"


def evaluate_core_satellite(
    portfolio: PortfolioSummary,
    strategy: dict,
) -> CoreSatelliteSummary | None:
    cfg = strategy.get("core_satellite") or {}
    if not cfg.get("enabled", False):
        return None

    broad_kw = cfg.get("broad_index_keywords") or [
        "沪深300",
        "中证500",
        "A500",
        "上证50",
        "红利",
        "500信息",
        "500信息技术",
    ]
    core_target = float(cfg.get("core_target_ratio", 0.70)) * 100
    satellite_target = float(cfg.get("satellite_target_ratio", 0.20)) * 100
    hedge_target = float(cfg.get("hedge_target_ratio", 0.10)) * 100
    threshold = float(cfg.get("rebalance_threshold", 0.05)) * 100

    role_weight = {"core": 0.0, "satellite": 0.0, "hedge": 0.0, "other": 0.0}
    for p in portfolio.positions:
        role = _role_for_position(p.fund_code, p.fund_name, cfg, broad_kw)
        if role in role_weight:
            role_weight[role] += p.weight_pct
        else:
            role_weight["other"] += p.weight_pct

    hints: list[str] = []
    needs = False
    checks = [
        ("core", role_weight["core"], core_target, "宽基核心"),
        ("satellite", role_weight["satellite"], satellite_target, "行业卫星"),
        ("hedge", role_weight["hedge"], hedge_target, "防御/海外"),
    ]
    for _role, actual, target, label in checks:
        drift = actual - target
        if abs(drift) > threshold:
            needs = True
            if drift > 0:
                hints.append(
                    f"{label} 实际 {actual:.1f}% 高于目标 {target:.0f}%（偏离 +{drift:.1f}%），"
                    f"建议减卫星/增宽基或再平衡"
                )
            else:
                hints.append(
                    f"{label} 实际 {actual:.1f}% 低于目标 {target:.0f}%（偏离 {drift:.1f}%），"
                    f"建议优先加仓该层"
                )

    if role_weight["other"] > 1:
        hints.append(f"未分类仓位 {role_weight['other']:.1f}%，请在 core_satellite 配置中归类")

    if not hints and portfolio.positions:
        hints.append(
            f"核心-卫星结构正常：宽基 {role_weight['core']:.1f}% / "
            f"卫星 {role_weight['satellite']:.1f}% / 防御 {role_weight['hedge']:.1f}%"
        )

    return CoreSatelliteSummary(
        core_target_pct=core_target,
        satellite_target_pct=satellite_target,
        hedge_target_pct=hedge_target,
        core_actual_pct=round(role_weight["core"], 2),
        satellite_actual_pct=round(role_weight["satellite"], 2),
        hedge_actual_pct=round(role_weight["hedge"], 2),
        unclassified_pct=round(role_weight["other"], 2),
        rebalance_threshold_pct=threshold,
        needs_rebalance=needs,
        hints=hints,
    )
