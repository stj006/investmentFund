"""市场数据刷新判断（无其它 collectors 依赖）。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def needs_fresh_market_data(latest_market_date: date) -> bool:
    """北京时间 18:00 后，若市场数据日期早于今天，应尝试刷新。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.hour < 18:
        return False
    return latest_market_date < now.date()
