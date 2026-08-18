#!/usr/bin/env python3
"""每日新闻汇总，供 Cursor Automation 写入 Linear。

用法（项目根目录）:
    python scripts/daily_news_linear.py
    python scripts/daily_news_linear.py --json
    python scripts/daily_news_linear.py --no-ai
    python scripts/daily_news_linear.py --count 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.advisor.news_summarizer import build_news_digest
from src.config_loader import load_fund_universe, load_positions, load_strategy

LINEAR_TEAM = "stj"
LINEAR_PROJECT = "新闻推荐"
DEFAULT_COUNT = 5
MIN_COUNT = 3


def issue_title(for_date: date | None = None) -> str:
    d = for_date or date.today()
    return f"[Daily News] {d.isoformat()}"


def format_news_markdown(items: list[dict], *, generated_at: str) -> str:
    lines = [
        f"## 今日要闻 ({generated_at})",
        "",
    ]
    for i, row in enumerate(items, start=1):
        title = row.get("title") or "（无标题）"
        summary = row.get("summary") or row.get("content_preview") or title
        url = (row.get("url") or "").strip()
        source = (row.get("source") or "").strip()
        published = (row.get("published_at") or "").strip()
        meta_parts = [p for p in (source, published) if p]
        meta = " · ".join(meta_parts)

        lines.append(f"### {i}. {title}")
        lines.append("")
        lines.append(summary)
        lines.append("")
        if url:
            lines.append(f"[阅读原文]({url})")
        if meta:
            lines.append(f"")
            lines.append(f"*{meta}*")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def select_top_items(digest: list[dict], count: int) -> list[dict]:
    target = max(MIN_COUNT, min(count, DEFAULT_COUNT))
    if len(digest) <= target:
        return digest
    return digest[:target]


def build_payload(*, use_llm: bool = True, count: int = DEFAULT_COUNT) -> dict:
    strategy = load_strategy()
    positions = load_positions()
    universe = load_fund_universe()

    digest, fetch_err = build_news_digest(
        strategy,
        positions,
        universe,
        use_llm=use_llm,
    )
    items = select_top_items(digest, count)
    today = date.today()
    generated_at = today.isoformat()

    return {
        "date": generated_at,
        "title": issue_title(today),
        "team": LINEAR_TEAM,
        "project": LINEAR_PROJECT,
        "items": items,
        "description": format_news_markdown(items, generated_at=generated_at),
        "fetch_error": fetch_err,
        "item_count": len(items),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成每日新闻摘要（Linear 推送用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 Automation 解析）")
    parser.add_argument("--no-ai", action="store_true", help="不调用 LLM，用内容预览作摘要")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="新闻条数（3-5，默认 5）")
    args = parser.parse_args()

    count = max(MIN_COUNT, min(args.count, DEFAULT_COUNT))
    payload = build_payload(use_llm=not args.no_ai, count=count)

    if payload["item_count"] < MIN_COUNT:
        print(
            f"警告：仅采集到 {payload['item_count']} 条新闻（目标 {MIN_COUNT}-{DEFAULT_COUNT} 条）",
            file=sys.stderr,
        )
        if payload.get("fetch_error"):
            print(f"采集异常：{payload['fetch_error']}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["description"])
        if payload.get("fetch_error"):
            print(f"\n采集异常：{payload['fetch_error']}", file=sys.stderr)

    return 0 if payload["item_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
