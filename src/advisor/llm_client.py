"""OpenAI 兼容 LLM 客户端（支持 DeepSeek、通义等）。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


class LlmEmptyResponseError(RuntimeError):
    """模型返回空内容或无法解析为 JSON。"""


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def is_llm_configured() -> bool:
    _load_env()
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def chat_json(
    system: str,
    user: str,
    *,
    max_retries: int | None = None,
) -> tuple[dict, str]:
    """调用 LLM，期望返回 JSON 对象。返回 (parsed_dict, raw_text)。

    空响应 / 非 JSON 时自动重试；仍失败则抛出 LlmEmptyResponseError。
    """
    _load_env()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未配置 LLM：请在 .env 中设置 LLM_API_KEY（或 OPENAI_API_KEY）"
        )

    from openai import OpenAI

    from src.advisor.validator import extract_json

    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    if max_retries is None:
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    last_raw = ""
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"LLM 请求失败（已重试 {max_retries} 次）: {e}") from e

        choice = resp.choices[0] if resp.choices else None
        raw = ""
        finish = ""
        if choice is not None:
            raw = (choice.message.content or "").strip()
            finish = getattr(choice, "finish_reason", None) or ""
        last_raw = raw

        if not raw:
            last_err = LlmEmptyResponseError(
                f"LLM 返回空内容（finish_reason={finish or 'unknown'}，"
                f"attempt={attempt}/{max_retries}）"
            )
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            break

        try:
            return json.loads(raw), raw
        except json.JSONDecodeError:
            try:
                return extract_json(raw), raw
            except (json.JSONDecodeError, ValueError) as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                break

    preview = (last_raw[:200] + "…") if len(last_raw) > 200 else last_raw
    raise LlmEmptyResponseError(
        f"LLM 无法解析为 JSON（已重试 {max_retries} 次）: {last_err}; raw={preview!r}"
    )
