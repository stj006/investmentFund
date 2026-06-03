"""动态回撤止盈：浮盈达标后监控最高点回撤，触发则建议止盈。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from src.collectors.nav import CACHE_DIR as NAV_CACHE_DIR, _load_cache as _load_nav_cache

NAV_TRAIL_DAYS = 60  # 回撤监控回看净值天数


@dataclass
class TrailingStopSignal:
    fund_code: str
    fund_name: str
    current_nav: float
    peak_nav: float
    drawdown_pct: float  # 负值
    profit_pct: float
    triggered: bool


def _nav_history(fund_code: str, lookback: int) -> list[dict]:
    cache_file = NAV_CACHE_DIR / f"{fund_code}.csv"
    if not cache_file.exists():
        return []
    df = _load_nav_cache(cache_file)
    if df is None or df.empty:
        return []
    cutoff = pd.Timestamp(date.today() - timedelta(days=lookback))
    df = df[df["净值日期"] >= cutoff].sort_values("净值日期")
    return [
        {"date": row["净值日期"].strftime("%Y-%m-%d"), "nav": float(row["单位净值"])}
        for _, row in df.iterrows()
        if pd.notna(row["单位净值"])
    ]


def check_trailing_stop(
    fund_code: str,
    fund_name: str,
    current_nav: float,
    profit_pct: float,
    strategy: dict,
) -> TrailingStopSignal | None:
    ts_cfg = strategy.get("trailing_stop") or {}
    if not ts_cfg.get("enabled", True):
        return None
    trigger_profit = float(ts_cfg.get("trigger_profit_pct", 0.20))
    max_dd = float(ts_cfg.get("max_drawdown_pct", 0.10))
    if profit_pct < trigger_profit * 100:
        return None
    points = _nav_history(fund_code, NAV_TRAIL_DAYS)
    if len(points) < 5:
        return None
    navs = [p["nav"] for p in points]
    peak = max(navs)
    dd_pct = (current_nav - peak) / peak if peak > 0 else 0.0
    return TrailingStopSignal(
        fund_code=fund_code,
        fund_name=fund_name,
        current_nav=round(current_nav, 4),
        peak_nav=round(peak, 4),
        drawdown_pct=round(dd_pct * 100, 2),
        profit_pct=round(profit_pct, 2),
        triggered=dd_pct <= -max_dd,
    )
