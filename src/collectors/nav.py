"""通过 AkShare 拉取开放式基金单位净值。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "nav"


@dataclass
class FundNavSnapshot:
    fund_code: str
    nav_date: date
    unit_nav: float
    daily_growth_pct: float | None  # 日增长率，单位 %
    prev_nav_date: date | None
    prev_unit_nav: float | None


def _parse_nav_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["净值日期"] = pd.to_datetime(df["净值日期"])
    df = df.sort_values("净值日期").reset_index(drop=True)
    df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
    if "日增长率" in df.columns:
        df["日增长率"] = pd.to_numeric(df["日增长率"], errors="coerce")
    return df.dropna(subset=["单位净值"])


def fetch_fund_nav_history(fund_code: str) -> pd.DataFrame:
    """拉取基金全部历史单位净值（东方财富）。"""
    raw = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    return _parse_nav_df(raw)


def _cache_path(fund_code: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{fund_code}.csv"


def get_fund_nav_snapshot(fund_code: str, use_cache: bool = True) -> FundNavSnapshot:
    cache_file = _cache_path(fund_code)
    if use_cache and cache_file.exists():
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if (datetime.now() - mtime).total_seconds() < 3600:
            df = _parse_nav_df(pd.read_csv(cache_file, encoding="utf-8-sig"))
        else:
            df = fetch_fund_nav_history(fund_code)
            df.to_csv(cache_file, index=False, encoding="utf-8-sig")
    else:
        df = fetch_fund_nav_history(fund_code)
        df.to_csv(cache_file, index=False, encoding="utf-8-sig")

    latest = df.iloc[-1]
    nav_date = latest["净值日期"].date()
    unit_nav = float(latest["单位净值"])
    growth = float(latest["日增长率"]) if pd.notna(latest.get("日增长率")) else None

    prev_date = None
    prev_nav = None
    if len(df) >= 2:
        prev = df.iloc[-2]
        prev_date = prev["净值日期"].date()
        prev_nav = float(prev["单位净值"])

    if growth is None and prev_nav and prev_nav > 0:
        growth = (unit_nav - prev_nav) / prev_nav * 100

    return FundNavSnapshot(
        fund_code=fund_code,
        nav_date=nav_date,
        unit_nav=unit_nav,
        daily_growth_pct=growth,
        prev_nav_date=prev_date,
        prev_unit_nav=prev_nav,
    )


def fetch_all_snapshots(fund_codes: list[str]) -> dict[str, FundNavSnapshot]:
    result: dict[str, FundNavSnapshot] = {}
    for code in fund_codes:
        result[code] = get_fund_nav_snapshot(code)
    return result
