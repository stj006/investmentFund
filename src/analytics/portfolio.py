"""持仓盈亏与仓位计算。"""

from __future__ import annotations

from dataclasses import dataclass

from src.collectors.index_benchmark import IndexSnapshot
from src.collectors.nav import FundNavSnapshot


@dataclass
class PositionMetrics:
    fund_code: str
    fund_name: str
    channel: str
    shares: float
    cost_per_share: float
    unit_nav: float
    nav_date: str
    market_value: float
    cost_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    daily_growth_pct: float | None
    weight_pct: float  # 占账户总市值


@dataclass
class PortfolioSummary:
    total_market_value: float
    total_cost_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    positions: list[PositionMetrics]
    benchmark: IndexSnapshot | None


def _pct(value: float) -> float:
    return round(value * 100, 2)


def build_portfolio_summary(
    positions_cfg: list[dict[str, str]],
    nav_map: dict[str, FundNavSnapshot],
    benchmark: IndexSnapshot | None = None,
) -> PortfolioSummary:
    rows: list[PositionMetrics] = []
    total_mv = 0.0
    total_cost = 0.0

    for pos in positions_cfg:
        code = pos["fund_code"]
        shares = float(pos["shares"])
        cost = float(pos["cost_per_share"])
        snap = nav_map[code]

        market_value = shares * snap.unit_nav
        cost_value = shares * cost
        pnl = market_value - cost_value
        pnl_pct = (snap.unit_nav - cost) / cost * 100 if cost > 0 else 0.0

        total_mv += market_value
        total_cost += cost_value

        rows.append(
            PositionMetrics(
                fund_code=code,
                fund_name=pos.get("fund_name", code),
                channel=pos.get("channel", ""),
                shares=shares,
                cost_per_share=cost,
                unit_nav=snap.unit_nav,
                nav_date=str(snap.nav_date),
                market_value=round(market_value, 2),
                cost_value=round(cost_value, 2),
                unrealized_pnl=round(pnl, 2),
                unrealized_pnl_pct=round(pnl_pct, 2),
                daily_growth_pct=snap.daily_growth_pct,
                weight_pct=0.0,
            )
        )

    for row in rows:
        row.weight_pct = _pct(row.market_value / total_mv) if total_mv > 0 else 0.0

    total_pnl = total_mv - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    return PortfolioSummary(
        total_market_value=round(total_mv, 2),
        total_cost_value=round(total_cost, 2),
        total_unrealized_pnl=round(total_pnl, 2),
        total_unrealized_pnl_pct=round(total_pnl_pct, 2),
        positions=rows,
        benchmark=benchmark,
    )


@dataclass
class WatchlistItem:
    fund_code: str
    fund_name: str
    theme: str
    risk_tag: str
    notes: str
    unit_nav: float
    nav_date: str
    daily_growth_pct: float | None


def build_watchlist(
    universe_cfg: list[dict[str, str]],
    nav_map: dict[str, FundNavSnapshot],
    held_codes: set[str],
) -> list[WatchlistItem]:
    items: list[WatchlistItem] = []
    for row in universe_cfg:
        code = row["fund_code"]
        if code in held_codes:
            continue
        snap = nav_map.get(code)
        if not snap:
            continue
        items.append(
            WatchlistItem(
                fund_code=code,
                fund_name=row.get("fund_name", code),
                theme=row.get("theme", ""),
                risk_tag=row.get("risk_tag", ""),
                notes=row.get("notes", ""),
                unit_nav=snap.unit_nav,
                nav_date=str(snap.nav_date),
                daily_growth_pct=snap.daily_growth_pct,
            )
        )
    return items
