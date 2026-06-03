"""市场数据刷新判断（无其它 collectors 依赖）。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def needs_fresh_market_data(latest_market_date: date) -> bool:
    """北京时间收盘后（16:00 起），若数据日期仍早于今天，应尝试从网络刷新。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    today = now.date()
    if latest_market_date >= today:
        return False
    # 16:00 前：上一交易日 K 线仍可能是最新公布，不强制刷新
    if now.hour < 16:
        return False
    return latest_market_date < today
