"""行业卫星层（方案 B：双卫星 主 25% + 次 15%）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.analytics.portfolio import PortfolioSummary, PositionMetrics


@dataclass
class SatelliteHolding:
    fund_code: str
    fund_name: str
    market_value: float
    managed_pct: float
    slot: str  # primary | secondary | overflow

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SatelliteSleeveSummary:
    mode: str
    total_target_pct: float
    primary_target_pct: float
    secondary_target_pct: float
    total_actual_pct: float
    primary_actual_pct: float
    secondary_actual_pct: float
    overflow_pct: float
    primary: SatelliteHolding | None
    secondary: SatelliteHolding | None
    others: list[SatelliteHolding]
    max_rotations_per_month: int
    min_hold_days: int
    exit_via_core: bool
    candidate_codes: list[str]
    needs_adjust: bool
    hints: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def evaluate_satellite_sleeve(
    portfolio: PortfolioSummary,
    strategy: dict,
    *,
    satellite_positions: list[PositionMetrics],
    managed_value: float,
) -> SatelliteSleeveSummary | None:
    cs = strategy.get("core_satellite") or {}
    sleeve = strategy.get("satellite_sleeve") or {}
    if not sleeve.get("enabled", True):
        return None

    mode = str(sleeve.get("mode", "dual")).lower()
    total_target = float(sleeve.get("total_ratio", cs.get("satellite_target_ratio", 0.40))) * 100
    primary_target = float(sleeve.get("primary_ratio", 0.25)) * 100
    secondary_target = float(sleeve.get("secondary_ratio", 0.15)) * 100
    max_single = float(sleeve.get("max_single_satellite_ratio", 0.28)) * 100
    threshold = float(cs.get("rebalance_threshold", 0.05)) * 100
    max_rotations = int(sleeve.get("max_rotations_per_month", 1))
    min_hold_days = int(sleeve.get("min_hold_days", 30))
    exit_via_core = bool(sleeve.get("exit_via_core", True))
    candidates = [str(c).zfill(6) for c in (sleeve.get("candidate_codes") or [])]

    denom = managed_value if managed_value > 0 else 1.0
    preferred_primary = str(sleeve.get("primary_preferred") or "").zfill(6)
    preferred_secondary = str(sleeve.get("secondary_preferred") or "").zfill(6)
    if preferred_primary == "000000":
        preferred_primary = ""
    if preferred_secondary == "000000":
        preferred_secondary = ""

    by_code = {str(p.fund_code).zfill(6): p for p in satellite_positions}
    ranked = sorted(satellite_positions, key=lambda p: p.market_value, reverse=True)
    slot_of: dict[str, str] = {}

    if preferred_primary and preferred_primary in by_code:
        slot_of[preferred_primary] = "primary"
    if preferred_secondary and preferred_secondary in by_code and preferred_secondary not in slot_of:
        slot_of[preferred_secondary] = "secondary"

    for p in ranked:
        code = str(p.fund_code).zfill(6)
        if code in slot_of:
            continue
        if "primary" not in slot_of.values():
            slot_of[code] = "primary"
        elif "secondary" not in slot_of.values():
            slot_of[code] = "secondary"
        else:
            slot_of[code] = "overflow"

    holdings: list[SatelliteHolding] = []
    for p in ranked:
        code = str(p.fund_code).zfill(6)
        pct = p.market_value / denom * 100.0
        holdings.append(
            SatelliteHolding(
                fund_code=p.fund_code,
                fund_name=p.fund_name,
                market_value=round(p.market_value, 2),
                managed_pct=round(pct, 2),
                slot=slot_of.get(code, "overflow"),
            )
        )

    primary = next((h for h in holdings if h.slot == "primary"), None)
    secondary = next((h for h in holdings if h.slot == "secondary"), None)
    others = [h for h in holdings if h.slot == "overflow"]
    total_actual = sum(h.managed_pct for h in holdings)
    primary_pct = primary.managed_pct if primary else 0.0
    secondary_pct = secondary.managed_pct if secondary else 0.0
    overflow_pct = sum(h.managed_pct for h in others)

    hints: list[str] = []
    needs = False

    if mode == "dual":
        hints.append(
            f"卫星层方案 B（双卫星）：目标主仓 {primary_target:.0f}% + 次席 {secondary_target:.0f}% "
            f"= 合计 {total_target:.0f}%（相对管理仓）"
        )

        if total_actual > total_target + threshold:
            needs = True
            hints.append(
                f"卫星合计 {total_actual:.1f}% 高于 {total_target:.0f}%，"
                f"建议减仓，利润优先转入真宽基 110020/022430"
            )
        elif total_actual < total_target - threshold and total_actual > 0:
            needs = True
            hints.append(
                f"卫星合计 {total_actual:.1f}% 低于 {total_target:.0f}%，"
                f"可用新增资金或宽基再平衡补卫星（先主后次）"
            )

        if primary and primary_pct > primary_target + threshold:
            needs = True
            hints.append(
                f"主卫星 {primary.fund_code} {primary.fund_name} 占管理仓 {primary_pct:.1f}% "
                f"高于目标 {primary_target:.0f}%，建议减至约 {primary_target:.0f}%，"
                f"腾出份额给次席或回宽基"
            )

        if primary and not secondary and primary_pct > max_single:
            needs = True
            hints.append(
                f"当前仅 1 只行业卫星且仓位 {primary_pct:.1f}% > 单卫星软上限 {max_single:.0f}%，"
                f"建议分出约 {secondary_target:.0f}% 建次席（候选："
                f"{', '.join(candidates[:4]) or '见 fund_universe satellite'}）"
            )
        elif primary and not secondary and mode == "dual":
            needs = True
            hints.append(
                f"双卫星模式缺少次席：建议用管理仓约 {secondary_target:.0f}% "
                f"配置第二行业（候选：{', '.join(candidates[:4]) or '004253 黄金'}），"
                f"或暂放宽基等待趋势信号"
            )

        if secondary and abs(secondary_pct - secondary_target) > threshold:
            if secondary_pct > secondary_target + threshold:
                needs = True
                hints.append(
                    f"次席 {secondary.fund_code} 占 {secondary_pct:.1f}% "
                    f"高于目标 {secondary_target:.0f}%，可减仓或与主仓再平衡"
                )
            elif secondary_pct < secondary_target - threshold:
                needs = True
                hints.append(
                    f"次席 {secondary.fund_code} 占 {secondary_pct:.1f}% "
                    f"低于目标 {secondary_target:.0f}%，趋势仍在可小幅补到目标"
                )

        if others:
            needs = True
            codes = "、".join(f"{h.fund_code}" for h in others)
            hints.append(
                f"卫星超过 2 只（{codes}），方案 B 仅保留主+次；"
                f"其余建议减仓并入主/次或转回宽基"
            )

        hints.append(
            f"轮动纪律：每月最多换行业 {max_rotations} 次；"
            f"持有满 {min_hold_days} 天再换；"
            + ("换出时先回宽基再进新行业。" if exit_via_core else "可直接高切低换行业。")
        )

    else:  # single
        hints.append(f"卫星层单赛道模式：合计目标 {total_target:.0f}%")
        if primary and primary_pct > max_single + threshold:
            needs = True
            hints.append(
                f"单卫星 {primary.fund_code} 占 {primary_pct:.1f}% "
                f"超过软上限 {max_single:.0f}%"
            )

    if not needs and holdings:
        p_txt = f"{primary.fund_code} {primary_pct:.1f}%" if primary else "无"
        s_txt = f"{secondary.fund_code} {secondary_pct:.1f}%" if secondary else "无"
        hints.append(f"双卫星结构可接受：主 {p_txt} / 次 {s_txt} / 合计 {total_actual:.1f}%")

    return SatelliteSleeveSummary(
        mode=mode,
        total_target_pct=total_target,
        primary_target_pct=primary_target,
        secondary_target_pct=secondary_target,
        total_actual_pct=round(total_actual, 2),
        primary_actual_pct=round(primary_pct, 2),
        secondary_actual_pct=round(secondary_pct, 2),
        overflow_pct=round(overflow_pct, 2),
        primary=primary,
        secondary=secondary,
        others=others,
        max_rotations_per_month=max_rotations,
        min_hold_days=min_hold_days,
        exit_via_core=exit_via_core,
        candidate_codes=candidates,
        needs_adjust=needs,
        hints=hints,
    )
