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


def check_valuation_take_profit(
    strategy: dict,
) -> ValuationSignal | None:
    cfg = strategy.get("valuation_take_profit") or {}
    if not cfg.get("enabled", False):
        return None
    index_code = str(cfg.get("index_code", "000300.SH"))
    threshold = float(cfg.get("pe_percentile_threshold", 0.80))
    index_name = "沪深300" if "000300" in index_code else index_code
    df = _fetch_index_pe(index_code)
    if df is None or df.empty:
        return ValuationSignal(
            index_code=index_code,
            index_name=index_name,
            pe_ttm=None,
            pe_percentile=None,
            threshold_pct=threshold * 100,
            triggered=False,
            hint="指数估值数据暂不可用，估值止盈跳过",
        )
    if "PE" in df.columns and "分位" in df.columns:
        latest = df.dropna(subset=["PE", "分位"]).iloc[-1]
        pe_ttm = float(latest["PE"])
        pe_pct = float(latest["分位"]) / 100.0 if latest["分位"] > 1 else float(latest["分位"])
    elif "PE" in df.columns:
        pe_series = df["PE"].dropna()
        if len(pe_series) < 10:
            return None
        pe_ttm = float(pe_series.iloc[-1])
        pe_pct = (pe_series > pe_ttm).mean()
    else:
        return None
    _save_pe_cache(index_code, df)
    triggered = pe_pct >= threshold
    hint = (
        f"{index_name} PE-TTM {pe_ttm:.1f}，分位 {pe_pct*100:.0f}% ≥ {threshold*100:.0f}%，"
        f"市场估值进入高位，建议分批止盈。"
        if triggered
        else f"{index_name} PE-TTM {pe_ttm:.1f}，分位 {pe_pct*100:.0f}% < {threshold*100:.0f}%，"
        f"估值未达高位，暂不止盈。"
    )
    return ValuationSignal(
        index_code=index_code,
        index_name=index_name,
        pe_ttm=round(pe_ttm, 1),
        pe_percentile=round(pe_pct * 100, 1),
        threshold_pct=threshold * 100,
        triggered=triggered,
        hint=hint,
    )
