"""估值止盈：基于基准指数 PE-TTM 分位，高位提示止盈。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd

from src.collectors.index_benchmark import _cache_path, _normalize_index_code
from src.config_loader import ROOT

PE_CACHE_DIR = ROOT / "data" / "pe"
PE_CACHE_MAX_DAYS = 7  # PE 数据 7 天内可用


@dataclass
class PeSnapshot:
    index_code: str
    index_name: str
    pe_ttm: float | None
    pe_percentile: float | None  # 0-1


@dataclass
class ValuationSignal:
    index_code: str
    index_name: str
    pe_ttm: float | None
    pe_percentile: float | None  # 0-100
    threshold_pct: float  # 配置的阈值
    triggered: bool
    hint: str


def _cache_pe_path(index_code: str) -> Path:
    PE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    symbol = _normalize_index_code(index_code)
    return PE_CACHE_DIR / f"{symbol}_pe.csv"


def _fetch_index_pe(index_code: str) -> pd.DataFrame | None:
    symbol = _normalize_index_code(index_code)
    try:
        df = ak.index_value_hist(symbol=symbol, indicator="市盈率")
        if df is None or df.empty:
            return None
        col_map = {
            "date": "日期",
            "日期": "日期",
            "value": "PE",
            "PE": "PE",
            "pe": "PE",
            "percentile": "分位",
            "分位": "分位",
        }
        rename = {c: col_map[c] for c in df.columns if c in col_map}
        df = df.rename(columns=rename)
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"])
        if "PE" in df.columns:
            df["PE"] = pd.to_numeric(df["PE"], errors="coerce")
        if "分位" in df.columns:
            df["分位"] = pd.to_numeric(df["分位"], errors="coerce")
        return df
    except Exception:
        return None


def _load_pe_cache(index_code: str) -> pd.DataFrame | None:
    path = _cache_pe_path(index_code)
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    age = (pd.Timestamp.now().timestamp() - mtime) / 86400
    if age > PE_CACHE_MAX_DAYS:
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return None


def _save_pe_cache(index_code: str, df: pd.DataFrame) -> None:
    path = _cache_pe_path(index_code)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def fetch_index_pe_snapshot(index_code: str) -> PeSnapshot:
    """拉取指数 PE 与历史分位（0-1），供估值止盈与智能定投共用。"""
    index_name = "沪深300" if "000300" in index_code else index_code
    df = _fetch_index_pe(index_code)
    if df is None or df.empty:
        return PeSnapshot(index_code=index_code, index_name=index_name, pe_ttm=None, pe_percentile=None)

    pe_ttm: float | None = None
    pe_pct: float | None = None
    if "PE" in df.columns and "分位" in df.columns:
        latest = df.dropna(subset=["PE", "分位"]).iloc[-1]
        pe_ttm = float(latest["PE"])
        raw = float(latest["分位"])
        pe_pct = raw / 100.0 if raw > 1 else raw
    elif "PE" in df.columns:
        pe_series = df["PE"].dropna()
        if len(pe_series) >= 10:
            pe_ttm = float(pe_series.iloc[-1])
            pe_pct = float((pe_series > pe_ttm).mean())

    if df is not None and not df.empty:
        _save_pe_cache(index_code, df)

    return PeSnapshot(
        index_code=index_code,
        index_name=index_name,
        pe_ttm=round(pe_ttm, 1) if pe_ttm is not None else None,
        pe_percentile=pe_pct,
    )


def check_valuation_take_profit(
    strategy: dict,
) -> ValuationSignal | None:
    cfg = strategy.get("valuation_take_profit") or {}
    if not cfg.get("enabled", False):
        return None
    index_code = str(cfg.get("index_code", "000300.SH"))
    threshold = float(cfg.get("pe_percentile_threshold", 0.80))
    very_high = float(cfg.get("pe_percentile_full_exit", 0.90))
    snap = fetch_index_pe_snapshot(index_code)
    if snap.pe_percentile is None:
        return ValuationSignal(
            index_code=index_code,
            index_name=snap.index_name,
            pe_ttm=None,
            pe_percentile=None,
            threshold_pct=threshold * 100,
            triggered=False,
            hint="指数估值数据暂不可用，估值止盈跳过",
        )

    pe_ttm = snap.pe_ttm
    pe_pct = snap.pe_percentile
    triggered = pe_pct >= threshold
    if pe_pct >= very_high:
        hint = (
            f"{snap.index_name} PE-TTM {pe_ttm:.1f}，分位 {pe_pct*100:.0f}% ≥ {very_high*100:.0f}%，"
            f"估值极高，建议卫星仓位大幅止盈，利润转入宽基核心。"
        )
    elif triggered:
        hint = (
            f"{snap.index_name} PE-TTM {pe_ttm:.1f}，分位 {pe_pct*100:.0f}% ≥ {threshold*100:.0f}%，"
            f"市场估值进入高位，建议分批止盈。"
        )
    else:
        hint = (
            f"{snap.index_name} PE-TTM {pe_ttm:.1f}，分位 {pe_pct*100:.0f}% < {threshold*100:.0f}%，"
            f"估值未达高位，暂不止盈。"
        )
    return ValuationSignal(
        index_code=index_code,
        index_name=snap.index_name,
        pe_ttm=pe_ttm,
        pe_percentile=round(pe_pct * 100, 1),
        threshold_pct=threshold * 100,
        triggered=triggered,
        hint=hint,
    )
