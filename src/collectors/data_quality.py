"""数据新鲜度提示（邮件 / 报告用）。"""

from __future__ import annotations

import html
from datetime import date

from src.collectors.index_benchmark import IndexSnapshot
from src.collectors.nav import FundNavSnapshot


def collect_stale_data_notes(
    nav_map: dict[str, FundNavSnapshot],
    benchmark: IndexSnapshot | None,
    data_as_of: str,
) -> tuple[str, str]:
    """返回 (plain_note, html_note)，无问题时为空字符串。"""
    lines: list[str] = []
    for code, snap in sorted(nav_map.items()):
        if snap.is_stale_cache:
            lines.append(f"{code} 使用{snap.data_source}（净值日 {snap.nav_date}）")
    if benchmark and benchmark.is_stale_cache:
        lines.append(
            f"沪深300 使用{benchmark.data_source}（交易日 {benchmark.trade_date}）"
        )

    today = date.today().isoformat()
    if data_as_of < today and not lines:
        lines.append(f"部分净值尚未更新至 {today}，数据截至 {data_as_of}")

    if not lines:
        return "", ""

    plain = "【数据说明】" + "；".join(lines) + "。请以完整报告中的净值日期为准。"
    html_note = (
        '<p style="color:#b45309;font-size:12px;background:#fffbeb;'
        'padding:8px;border-radius:4px">'
        f"<b>数据说明</b>：{html.escape('；'.join(lines))}。"
        "请以完整报告中的净值日期为准。</p>"
    )
    return plain, html_note
