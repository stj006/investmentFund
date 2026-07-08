"""再平衡提醒节流：避免每日重复刷 REBALANCE。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config_loader import CONFIG_DIR

STATE_PATH = CONFIG_DIR / "rebalance_state.json"


def load_rebalance_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"last_signaled_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_signaled_at": None}


def days_since_last_signal() -> int | None:
    raw = load_rebalance_state().get("last_signaled_at")
    if not raw:
        return None
    try:
        last = date.fromisoformat(str(raw))
        return (date.today() - last).days
    except ValueError:
        return None


def should_signal_rebalance(interval_days: int) -> bool:
    if interval_days <= 0:
        return True
    elapsed = days_since_last_signal()
    if elapsed is None:
        return True
    return elapsed >= interval_days


def mark_rebalance_signaled() -> None:
    payload = {
        "last_signaled_at": date.today().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
