"""加载 config 目录下的 YAML 与 CSV 配置。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load_strategy() -> dict[str, Any]:
    path = CONFIG_DIR / "strategy.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_csv_rows(filename: str) -> list[dict[str, str]]:
    path = CONFIG_DIR / filename
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("fund_code") or "").strip()
            if not code:
                continue
            cleaned = {k: (v or "").strip() for k, v in row.items()}
            cleaned["fund_code"] = code
            rows.append(cleaned)
    return rows


def load_positions() -> list[dict[str, str]]:
    return _read_csv_rows("positions.csv")


def load_fund_universe() -> list[dict[str, str]]:
    return _read_csv_rows("fund_universe.csv")


def all_fund_codes() -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for row in load_positions() + load_fund_universe():
        code = row["fund_code"]
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes
