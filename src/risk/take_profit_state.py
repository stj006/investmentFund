"""分批止盈档位状态：每档只提醒一次，避免重复信号。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config_loader import CONFIG_DIR

STATE_PATH = CONFIG_DIR / "take_profit_state.json"


def load_take_profit_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"funds": {}, "updated_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        data.setdefault("funds", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"funds": {}, "updated_at": None}


def get_last_step_index(fund_code: str) -> int:
    code = str(fund_code).zfill(6)
    funds = load_take_profit_state().get("funds") or {}
    entry = funds.get(code) or {}
    return int(entry.get("last_step_index", -1))


def mark_step_signaled(fund_code: str, step_index: int) -> None:
    code = str(fund_code).zfill(6)
    state = load_take_profit_state()
    funds = dict(state.get("funds") or {})
    funds[code] = {
        "last_step_index": step_index,
        "last_signaled_at": date.today().isoformat(),
    }
    payload = {
        "funds": funds,
        "updated_at": datetime.now().isoformat(),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def next_step_to_signal(
    fund_code: str,
    pnl_ratio: float,
    steps: list[float],
) -> int | None:
    """返回下一个应提醒的档位索引；已全部提醒则 None。"""
    if not steps or pnl_ratio <= 0:
        return None
    sorted_steps = sorted(float(s) for s in steps)
    last = get_last_step_index(fund_code)
    candidate = last + 1
    if candidate >= len(sorted_steps):
        return None
    if pnl_ratio >= sorted_steps[candidate]:
        return candidate
    return None
