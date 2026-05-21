"""基准指数行情（沪深300 等），多数据源 + 本地缓存。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

from src.config_loader import ROOT

INDEX_SYMBOL_MAP = {
    "000300.SH": "000300",
    "000300": "000300",
    "399006.SZ": "399006",
}

# 东方财富日线代码
INDEX_EM_SYMBOL = {
    "000300": "sh000300",
    "399006": "sz399006",
}

CACHE_DIR = ROOT / "data" / "index"
CACHE_MAX_AGE_HOURS = 12
STALE_CACHE_MAX_DAYS = 7


@dataclass
class IndexSnapshot:
    index_code: str
    trade_date: date
    close: float
    daily_change_pct: float | None
    name: str = "沪深300"
    data_source: str = ""

    @property
    def is_stale_cache(self) -> bool:
        return "缓存" in self.data_source


def _normalize_index_code(index_code: str) -> str:
    return INDEX_SYMBOL_MAP.get(index_code, index_code.replace(".SH", "").replace(".SZ", ""))


def _cache_path(symbol: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{symbol}.csv"


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """统一为 日期、收盘 列。"""
    df = df.copy()
    col_map = {
        "date": "日期",
        "日期": "日期",
        "close": "收盘",
        "收盘": "收盘",
        "Close": "收盘",
    }
    rename = {c: col_map[c] for c in df.columns if c in col_map}
    df = df.rename(columns=rename)
    if "日期" not in df.columns or "收盘" not in df.columns:
        raise ValueError(f"无法识别指数列: {list(df.columns)}")
    df["日期"] = pd.to_datetime(df["日期"])
    df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")
    return df.dropna(subset=["收盘"]).sort_values("日期").reset_index(drop=True)


def _snapshot_from_df(
    df: pd.DataFrame, index_code: str, symbol: str, source: str
) -> IndexSnapshot:
    latest = df.iloc[-1]
    trade_date = latest["日期"].date()
    close = float(latest["收盘"])
    daily_pct = None
    if len(df) >= 2:
        prev = float(df.iloc[-2]["收盘"])
        if prev > 0:
            daily_pct = (close - prev) / prev * 100
    name = "沪深300" if symbol == "000300" else symbol
    return IndexSnapshot(
        index_code=index_code,
        trade_date=trade_date,
        close=close,
        daily_change_pct=daily_pct,
        name=name,
        data_source=source,
    )


def _save_cache(symbol: str, df: pd.DataFrame) -> None:
    _cache_path(symbol).write_text(
        df.to_csv(index=False, encoding="utf-8-sig"),
        encoding="utf-8",
    )


def _load_cache(symbol: str, max_age_days: int | None = None) -> pd.DataFrame | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    if max_age_days is not None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(days=max_age_days):
            return None
    return _normalize_df(pd.read_csv(path, encoding="utf-8-sig"))


def _fetch_index_zh_a_hist(symbol: str) -> pd.DataFrame:
    return _normalize_df(ak.index_zh_a_hist(symbol=symbol, period="daily"))


def _fetch_stock_zh_index_daily(symbol: str) -> pd.DataFrame:
    em = INDEX_EM_SYMBOL.get(symbol, f"sh{symbol}")
    return _normalize_df(ak.stock_zh_index_daily(symbol=em))


def _fetch_index_daily_em(symbol: str) -> pd.DataFrame:
    """部分版本 AkShare 提供的东方财富指数日线。"""
    em = INDEX_EM_SYMBOL.get(symbol, f"sh{symbol}")
    raw = ak.index_zh_a_hist_em(symbol=em, period="daily")
    return _normalize_df(raw)


def _try_fetchers(symbol: str, retries: int = 2) -> tuple[pd.DataFrame, str]:
    fetchers: list[tuple[str, callable]] = [
        ("index_zh_a_hist", lambda: _fetch_index_zh_a_hist(symbol)),
        ("stock_zh_index_daily", lambda: _fetch_stock_zh_index_daily(symbol)),
    ]
    # index_zh_a_hist_em 部分环境可用
    try:
        fetchers.append(
            ("index_zh_a_hist_em", lambda: _fetch_index_daily_em(symbol))
        )
    except AttributeError:
        pass

    last_err: Exception | None = None
    for name, fn in fetchers:
        for attempt in range(retries):
            try:
                return fn(), name
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
    raise last_err or RuntimeError("所有指数数据源均失败")


def fetch_index_snapshot(
    index_code: str = "000300.SH",
    *,
    use_cache: bool = True,
    allow_stale_cache: bool = True,
) -> IndexSnapshot:
    symbol = _normalize_index_code(index_code)
    cache_file = _cache_path(symbol)

    if use_cache and cache_file.exists():
        age_h = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age_h < CACHE_MAX_AGE_HOURS:
            df = _load_cache(symbol)
            if df is not None and len(df) > 0:
                snap = _snapshot_from_df(df, index_code, symbol, "本地缓存")
                return snap

    try:
        df, source = _try_fetchers(symbol)
        _save_cache(symbol, df)
        return _snapshot_from_df(df, index_code, symbol, source)
    except Exception:
        if not allow_stale_cache:
            raise
        df = _load_cache(symbol, max_age_days=STALE_CACHE_MAX_DAYS)
        if df is not None and len(df) > 0:
            snap = _snapshot_from_df(
                df, index_code, symbol, f"过期缓存（≤{STALE_CACHE_MAX_DAYS}天）"
            )
            return snap
        raise
