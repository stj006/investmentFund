"""邮件通知配置（.env 优先，config/notify.yaml 兜底）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.config_loader import CONFIG_DIR, ROOT


@dataclass
class EmailSettings:
    enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    notify_to: str

    @property
    def is_ready(self) -> bool:
        return bool(
            self.enabled
            and self.smtp_user
            and self.smtp_password
            and self.notify_to
        )


def load_email_settings() -> EmailSettings:
    load_dotenv(ROOT / ".env")
    yaml_cfg: dict = {}
    notify_path = CONFIG_DIR / "notify.yaml"
    if notify_path.exists():
        with notify_path.open(encoding="utf-8") as f:
            yaml_cfg = (yaml.safe_load(f) or {}).get("email", {})

    def _bool(val: str | bool | None, default: bool) -> bool:
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("1", "true", "yes", "on")

    enabled = _bool(os.getenv("EMAIL_ENABLED"), _bool(yaml_cfg.get("enabled"), True))
    smtp_host = os.getenv("SMTP_HOST") or yaml_cfg.get("smtp_host") or "smtp.qq.com"
    smtp_port = int(os.getenv("SMTP_PORT") or yaml_cfg.get("smtp_port") or 465)
    smtp_user = os.getenv("SMTP_USER") or yaml_cfg.get("smtp_user") or ""
    smtp_password = os.getenv("SMTP_PASSWORD") or yaml_cfg.get("smtp_password") or ""
    notify_to = os.getenv("NOTIFY_TO") or yaml_cfg.get("to") or smtp_user

    # 未单独配置 SMTP_USER 时，默认用收件 QQ 邮箱发信
    if not smtp_user and notify_to:
        smtp_user = notify_to

    return EmailSettings(
        enabled=enabled,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        notify_to=notify_to,
    )
