#!/usr/bin/env python3
"""日报任务失败时发送告警邮件。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.notify.email import send_email
from src.notify.settings import load_email_settings


def main() -> int:
    settings = load_email_settings()
    if not settings.is_ready:
        print("告警邮件未发送：SMTP 未配置")
        return 1

    log_dir = ROOT / "logs"
    today = date.today().isoformat()
    log_file = log_dir / f"daily_{today}.log"
    tail = ""
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = "\n".join(lines[-30:])

    subject = f"【基金日报】{today} 任务失败告警"
    plain = (
        f"基金自动化日报任务于 {today} 执行失败。\n\n"
        f"请查看日志：{log_file}\n\n"
        f"--- 日志末尾 ---\n{tail}"
    )
    html = f"<pre>{plain}</pre>"
    try:
        send_email(settings, subject, plain, html)
        print(f"告警已发送至 {settings.notify_to}")
        return 0
    except Exception as e:
        print(f"告警发送失败: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
