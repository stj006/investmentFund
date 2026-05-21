"""OpenAI 兼容 LLM 客户端（支持 DeepSeek、通义等）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def is_llm_configured() -> bool:
    _load_env()
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def chat_json(system: str, user: str) -> tuple[dict, str]:
    """调用 LLM，期望返回 JSON 对象。返回 (parsed_dict, raw_text)。"""
    _load_env()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未配置 LLM：请在 .env 中设置 LLM_API_KEY（或 OPENAI_API_KEY）"
        )

    from openai import OpenAI

    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    from src.advisor.validator import extract_json

    raw = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        return extract_json(raw), raw
