"""Phase 3：根据 AI/规则建议生成可执行操作清单（半自动，需人工在 APP 确认）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.advisor.advisor import AdviceResult
from src.analytics.portfolio import PortfolioSummary, PositionMetrics
from src.config_loader import ROOT

CHECKLIST_DIR = ROOT / "data" / "checklist"

ACTION_LABELS = {
    "hold": "持有",
    "add": "加仓",
    "reduce": "减仓",
    "switch": "换基",
}


@dataclass
class OperationItem:
    fund_code: str
    fund_name: str
    channel: str
    action: str
    ratio: float | None
    shares: float | None  # 建议赎回/申购份额（估算）
    amount_cny: float | None  # 估算金额（元）
    reason: str
    steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _position_map(portfolio: PortfolioSummary) -> dict[str, PositionMetrics]:
    return {p.fund_code: p for p in portfolio.positions}


def _channel_for(code: str, positions_cfg: list[dict[str, str]]) -> str:
    for p in positions_cfg:
        if p["fund_code"] == code:
            return p.get("channel", "请自行选择渠道")
    return "请先在 fund_universe / positions 配置渠道"


def build_operation_checklist(
    portfolio: PortfolioSummary,
    advice: AdviceResult,
    positions_cfg: list[dict[str, str]],
    strategy: dict,
) -> list[OperationItem]:
    """将 advice.actions 转为带份额/金额估算的步骤清单。"""
    pos_map = _position_map(portfolio)
    trading = strategy.get("trading", {})
    max_buy = float(trading.get("max_daily_buy_amount", 10000))
    items: list[OperationItem] = []

    for act in advice.actions:
        code = act["fund_code"]
        action = act["action"]
        ratio = act.get("ratio")
        reason = act.get("reason", "")
        pos = pos_map.get(code)
        name = pos.fund_name if pos else code
        channel = pos.channel if pos else _channel_for(code, positions_cfg)
        nav = pos.unit_nav if pos else 0.0
        shares = pos.shares if pos else 0.0

        steps: list[str] = []
        est_shares: float | None = None
        est_amount: float | None = None

        if action == "hold":
            steps = [f"打开【{channel}】查看 {name}({code})，今日无需操作。"]
        elif action == "reduce" and pos and ratio:
            est_shares = round(shares * float(ratio), 2)
            est_amount = round(est_shares * nav, 2)
            steps = [
                f"1. 打开【{channel}】→ 我的持仓 → {name}({code})",
                f"2. 选择「赎回」",
                f"3. 建议赎回约 **{est_shares}** 份（约 **{est_amount:.2f}** 元，按最新净值估算）",
                "4. 确认费率与到账日，提交前请再次核对",
            ]
        elif action == "add":
            est_amount = round(
                min(max_buy, portfolio.total_market_value * float(ratio))
                if ratio
                else max_buy,
                2,
            )
            steps = [
                f"1. 打开【{channel}】→ 搜索基金 {name}({code})",
                f"2. 选择「申购/定投」",
                f"3. 建议申购约 **{est_amount:.2f}** 元（不超过策略单日上限 {max_buy:.0f} 元）",
                "4. 确认开放申购状态后提交",
            ]
        elif action == "switch":
            steps = [
                f"1. 换基需先赎回 {name}({code})，再申购目标基金（见邮件/报告换基候选）",
                "2. 注意 7 日赎回费与空窗期风险",
                "3. 建议间隔≥策略配置的换基冷却天数",
            ]
        else:
            steps = [f"请打开【{channel}】手动处理 {name}({code})：{ACTION_LABELS.get(action, action)}"]

        items.append(
            OperationItem(
                fund_code=code,
                fund_name=name,
                channel=channel,
                action=action,
                ratio=float(ratio) if ratio is not None else None,
                shares=est_shares,
                amount_cny=est_amount,
                reason=reason,
                steps=steps,
            )
        )

    # 无 AI 操作时：仅有规则预警也生成提示项
    if not items and advice.rule_signals:
        for sig in advice.rule_signals:
            if sig.severity not in ("warning", "critical") or not sig.fund_code:
                continue
            pos = pos_map.get(sig.fund_code)
            if not pos:
                continue
            items.append(
                OperationItem(
                    fund_code=sig.fund_code,
                    fund_name=pos.fund_name,
                    channel=pos.channel,
                    action=sig.suggested_action,
                    ratio=None,
                    shares=None,
                    amount_cny=None,
                    reason=sig.message,
                    steps=[
                        f"【规则提醒】{sig.message}",
                        f"请打开【{pos.channel}】查看 {pos.fund_name}，自行决定是否操作。",
                    ],
                )
            )

    return items


def render_checklist_markdown(
    report_date: date,
    items: list[OperationItem],
    advice: AdviceResult,
    portfolio: PortfolioSummary,
) -> str:
    lines = [
        f"# 今日操作清单 {report_date.isoformat()}",
        "",
        "> **semi_auto**：以下步骤需在支付宝/天天基金等 APP 中**手动确认**后执行，系统不会代下单。",
        "",
        f"- 账户市值：**{portfolio.total_market_value:,.2f}** 元",
        f"- 浮动盈亏：**{portfolio.total_unrealized_pnl:+,.2f}** 元（{portfolio.total_unrealized_pnl_pct:+.2f}%）",
        "",
    ]
    if advice.market_summary:
        lines.extend(["## AI 摘要", "", advice.market_summary, ""])

    if not items:
        lines.extend(["", "## 操作项", "", "今日无明确操作，建议持有观望。", ""])
        return "\n".join(lines)

    lines.extend(["", "## 操作项", ""])
    for i, op in enumerate(items, 1):
        label = ACTION_LABELS.get(op.action, op.action)
        lines.append(f"### {i}. {label} — {op.fund_name}（{op.fund_code}）")
        lines.append("")
        lines.append(f"- **渠道**：{op.channel}")
        if op.ratio is not None:
            lines.append(f"- **建议比例**：{op.ratio * 100:.0f}%")
        if op.shares is not None:
            lines.append(f"- **估算份额**：{op.shares} 份")
        if op.amount_cny is not None:
            lines.append(f"- **估算金额**：{op.amount_cny:,.2f} 元")
        lines.append(f"- **理由**：{op.reason}")
        lines.append("")
        for step in op.steps:
            lines.append(step)
        lines.append("")

    if advice.switch_candidates:
        lines.extend(["## 换基候选（仅供参考）", ""])
        for sw in advice.switch_candidates:
            lines.append(
                f"- {sw['from_fund_code']} → {sw['to_fund_code']}：{sw.get('reason', '')}"
            )
        lines.append("")

    lines.append("---")
    lines.append("完整日报见项目 `reports/` 目录或邮件正文。")
    return "\n".join(lines)


def save_checklist(content: str, report_date: date | None = None) -> Path:
    d = report_date or date.today()
    CHECKLIST_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKLIST_DIR / f"{d.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path
