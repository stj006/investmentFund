"""卫星逻辑退出复盘（SATELLITE_LOGIC_EXIT）：深亏触发复盘/减仓回宽基，默认不清仓。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.portfolio import PortfolioSummary, PositionMetrics


@dataclass
class SatelliteExitHint:
    fund_code: str
    fund_name: str
    unrealized_pnl_pct: float
    level: str  # review | reduce | deep_reduce
    suggested_reduce_ratio: float
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _is_satellite_position(
    p: PositionMetrics,
    role_by_code: dict[str, str],
    satellite_codes: set[str],
    excluded: set[str],
) -> bool:
    code = str(p.fund_code).zfill(6)
    if code in excluded:
        return False
    role = role_by_code.get(code, "")
    if role == "satellite":
        return True
    if role in ("core", "core_growth", "hedge", "pool"):
        return False
    return code in satellite_codes


def evaluate_satellite_logic_exits(
    portfolio: PortfolioSummary,
    strategy: dict,
    *,
    role_by_code: dict[str, str] | None = None,
    theme_by_code: dict[str, str] | None = None,
) -> list[SatelliteExitHint]:
    cfg = strategy.get("satellite_logic_exit") or {}
    if not cfg.get("enabled", False):
        return []

    role_by_code = role_by_code or {}
    theme_by_code = theme_by_code or {}
    cs = strategy.get("core_satellite") or {}
    satellite_codes = {str(c).zfill(6) for c in (cs.get("satellite_fund_codes") or [])}
    excluded = {str(c).zfill(6) for c in (cfg.get("exclude_codes") or [])}
    exclude_themes = {str(t).strip() for t in (cfg.get("exclude_themes") or [])}

    review_pct = float(cfg.get("review_loss_pct", -0.20)) * 100
    exit_pct = float(cfg.get("exit_loss_pct", -0.40)) * 100
    deep_pct = float(cfg.get("full_exit_loss_pct", -0.50)) * 100
    reduce_ratio = float(cfg.get("reduce_ratio", 0.33))
    deep_ratio = float(cfg.get("deep_reduce_ratio", 0.50))
    exit_via_core = bool(cfg.get("exit_via_core", True))
    core_txt = "利润/资金优先转入 110020/022430 真宽基" if exit_via_core else "可换入其他卫星候选"

    out: list[SatelliteExitHint] = []
    for p in portfolio.positions:
        code = str(p.fund_code).zfill(6)
        theme = theme_by_code.get(code) or theme_by_code.get(p.fund_code) or ""
        if theme in exclude_themes:
            continue
        if not _is_satellite_position(p, role_by_code, satellite_codes, excluded):
            continue

        pnl = p.unrealized_pnl_pct
        if pnl > review_pct:
            continue

        if pnl <= deep_pct:
            level = "deep_reduce"
            ratio = deep_ratio
            msg = (
                f"{p.fund_name} 浮亏 {pnl:.1f}% ≤ {deep_pct:.0f}%："
                f"请先确认行业逻辑是否失效；若叙事已坏，建议减仓约 {ratio*100:.0f}% 并{core_txt}；"
                f"若逻辑仍在，可保留观察、勿恐慌清仓"
            )
        elif pnl <= exit_pct:
            level = "reduce"
            ratio = reduce_ratio
            msg = (
                f"{p.fund_name} 浮亏 {pnl:.1f}% ≤ {exit_pct:.0f}%："
                f"触发卫星减仓复盘，建议减约 {ratio*100:.0f}% 回宽基（默认不清零）；"
                f"请人工确认主题逻辑是否仍成立；{core_txt}"
            )
        else:
            level = "review"
            ratio = 0.0
            msg = (
                f"{p.fund_name} 浮亏 {pnl:.1f}% 触及复盘线 {review_pct:.0f}%："
                f"检查政策/景气是否恶化；逻辑未坏则持有或小额补，勿因价格机械清仓"
            )

        out.append(
            SatelliteExitHint(
                fund_code=p.fund_code,
                fund_name=p.fund_name,
                unrealized_pnl_pct=pnl,
                level=level,
                suggested_reduce_ratio=ratio,
                message=msg,
            )
        )
    return out
