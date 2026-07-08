"""基金分类辅助函数。"""

from __future__ import annotations


def is_broad_index(name: str, keywords: list[str]) -> bool:
    return any(kw in name for kw in keywords)
