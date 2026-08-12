"""校验并清洗 LLM 返回的 JSON 建议。"""

from __future__ import annotations

import json
import re
from typing import Any

VALID_ACTIONS = frozenset({"hold", "add", "reduce", "switch"})
VALID_RISK = frozenset({"low", "medium", "high"})


def extract_json(text: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象；支持 markdown 代码块与前后杂质。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("LLM 输出为空，无法解析 JSON")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        raise ValueError(f"JSON 根类型应为 object，实际为 {type(obj).__name__}")
    except json.JSONDecodeError:
        pass

    # 截取首个完整 {...}（容忍前后说明文字）
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        obj = json.loads(chunk)
        if isinstance(obj, dict):
            return obj
        raise ValueError(f"截取 JSON 根类型应为 object，实际为 {type(obj).__name__}")

    raise ValueError("未找到可解析的 JSON 对象")


def validate_advice(raw: dict[str, Any], whitelist: set[str]) -> dict[str, Any]:
    market_summary = str(raw.get("market_summary") or "").strip()
    if not market_summary:
        raise ValueError("缺少 market_summary")

    risk = str(raw.get("overall_risk_level") or "medium").lower()
    if risk not in VALID_RISK:
        risk = "medium"

    actions_out: list[dict[str, Any]] = []
    for item in raw.get("actions") or []:
        code = str(item.get("fund_code") or "").strip()
        action = str(item.get("action") or "hold").lower()
        if code not in whitelist:
            continue
        if action not in VALID_ACTIONS:
            action = "hold"
        conf = float(item.get("confidence") or 0.5)
        conf = max(0.0, min(1.0, conf))
        ratio = item.get("ratio")
        if ratio is not None:
            ratio = max(0.0, min(1.0, float(ratio)))
        actions_out.append(
            {
                "fund_code": code,
                "action": action,
                "ratio": ratio,
                "reason": str(item.get("reason") or "").strip() or "无",
                "confidence": round(conf, 2),
                "rule_hits": list(item.get("rule_hits") or []),
                "requires_human_confirm": bool(
                    item.get("requires_human_confirm", True)
                ),
            }
        )

    switch_out: list[dict[str, Any]] = []
    for item in raw.get("switch_candidates") or []:
        to_code = str(item.get("to_fund_code") or "").strip()
        from_code = str(item.get("from_fund_code") or "").strip()
        if to_code not in whitelist or from_code not in whitelist:
            continue
        switch_out.append(
            {
                "from_fund_code": from_code,
                "to_fund_code": to_code,
                "reason": str(item.get("reason") or "").strip() or "无",
            }
        )

    return {
        "market_summary": market_summary,
        "overall_risk_level": risk,
        "actions": actions_out,
        "switch_candidates": switch_out,
    }
