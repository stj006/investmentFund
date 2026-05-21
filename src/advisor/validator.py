"""校验并清洗 LLM 返回的 JSON 建议。"""

from __future__ import annotations

import json
import re
from typing import Any

VALID_ACTIONS = frozenset({"hold", "add", "reduce", "switch"})
VALID_RISK = frozenset({"low", "medium", "high"})


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


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
