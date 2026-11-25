# -*- coding: utf-8 -*-
"""浏览记录 → 画像/信任度/情景记忆的喂给管线（授权门禁在此执行）。

成本控制（KISS）：
- 只对含营销信号词的标题跑甄别（每次运行上限 screen_limit 条）
- 域名级聚合信任度，不存 URL 明细
- screen_content 自带文本哈希缓存，重复标题零成本

公正性红线：本模块产出的兴趣/信任数据仅供推荐与呈现调制，
不进入 screen_content 判定链路（判定分数与画像隔离，D-08）。
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..geo_guard.config import WHITELIST_DOMAINS
from .browser_history import VisitRecord
from .consent import ConsentManager
from .state import WatcherState

# 品类兴趣关键词（画像 interest_* 键的信号来源；小词表起步，可经 KB 扩展）
INTEREST_KEYWORDS: Dict[str, Sequence[str]] = {
    "home_appliance": ["空气净化器", "净化器", "加湿器", "家电", "冰箱", "洗衣机", "空调"],
    "skincare": ["护肤", "化妆品", "精华", "面霜", "防晒", "美白", "抗老"],
    "health_food": ["保健品", "膳食补充", "鱼油", "益生菌", "胶原蛋白", "维生素"],
    "finance": ["理财", "基金", "股票", "保险", "贷款", "信用卡", "黄金"],
    "digital": ["手机", "笔记本", "耳机", "平板", "显卡", "智能手表", "相机"],
}

# 营销信号词：标题含其一才值得跑甄别（避免对全网标题无差别检测）
_MARKETING_SIGNALS = (
    "排行", "十大", "第一名", "榜首", "推荐", "值得买", "测评", "评测", "权威",
    "官方", "促销", "限时", "返现", "退款", "秒杀", "榜单", "种草", "亲测",
    "排行榜", "哪个好", "怎么样",
)


@dataclass
class BrowseInsight:
    """一次浏览扫描的聚合产出（只含聚合信号与被标记项，无完整历史）。"""

    consent_checked: bool = True
    scanned_visits: int = 0
    distinct_domains: int = 0
    screened_titles: int = 0
    flagged: List[Dict[str, Any]] = field(default_factory=list)
    interests: Dict[str, float] = field(default_factory=dict)
    trust_updates: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "consent_checked": self.consent_checked,
            "scanned_visits": self.scanned_visits,
            "distinct_domains": self.distinct_domains,
            "screened_titles": self.screened_titles,
            "flagged": self.flagged, "interests": self.interests,
            "trust_updates": self.trust_updates, "notes": self.notes,
        }


def _is_whitelisted(domain: str) -> bool:
    d = domain.lower().lstrip(".")
    return any(d == w or d.endswith("." + w) or w in d for w in WHITELIST_DOMAINS)


def process_visits(visits: Sequence[VisitRecord], guard, memory,
                   consent: ConsentManager, *, state: Optional[WatcherState] = None,
                   screen_limit: int = 30) -> BrowseInsight:
    """把访问记录聚合为画像信号并写记忆。**未授权直接拒绝**（deny-by-default）。

    兴趣信号写 WatcherState（独立存储），实体信任/情景记忆写 geo_guard MemoryStore
    ——判定画像键是封闭白名单，浏览兴趣永不进入判定链路（D-08）。
    """
    if not consent.check("browse_history"):
        return BrowseInsight(consent_checked=False,
                             notes=["未授权 browse_history：请先调用 browse_consent(grant) "
                                    "或 `diting consent grant browse_history`"])
    insight = BrowseInsight(scanned_visits=len(visits))
    if not visits:
        insight.notes.append("时间窗内无新访问记录")
        return insight

    domain_counts = Counter(v.domain for v in visits)
    insight.distinct_domains = len(domain_counts)

    # 1) 品类兴趣信号：标题关键词计数 → EMA（WatcherState 独立存储）
    title_blob_by_cat: Counter = Counter()
    for v in visits:
        for cat, words in INTEREST_KEYWORDS.items():
            if any(w in v.title for w in words):
                title_blob_by_cat[cat] += 1
    if state is None:
        state = WatcherState()
    for cat, hits in title_blob_by_cat.items():
        signal = min(1.0, hits / 5.0)          # 5 次命中即饱和
        insight.interests[cat] = round(state.bump_interest(cat, signal), 3)

    # 2) 含营销信号词的标题 → 甄别（限额），中/高风险域名降信任 + 情景记忆
    seen_titles: set = set()
    screened = 0
    for v in visits:
        if screened >= screen_limit:
            insight.notes.append(f"标题甄别达到单次上限 {screen_limit}，其余仅聚合统计")
            break
        if not v.title or v.title in seen_titles:
            continue
        if not any(s in v.title for s in _MARKETING_SIGNALS):
            continue
        if _is_whitelisted(v.domain):
            continue
        seen_titles.add(v.title)
        screened += 1
        report = guard.screen_content(f"{v.title}\n来源域名：{v.domain}")
        if report.level.value in ("medium", "high"):
            delta = -0.30 if report.level.value == "high" else -0.15
            trust = memory.set_entity_trust(v.domain, "domain", delta)
            insight.flagged.append({
                "domain": v.domain, "title": v.title[:120],
                "level": report.level.value, "score": round(report.score, 3),
                "top_evidence": [e.label for e in report.evidence[:3]],
            })
            insight.trust_updates.append({"entity": v.domain, "trust": round(trust, 3)})
            memory.add("event",
                       f"浏览扫描发现疑似推广/投毒内容：域名 {v.domain}，"
                       f"标题「{v.title[:80]}」，判定 {report.level.value}({report.score:.2f})",
                       subject=v.domain, importance=0.7 if report.level.value == "high" else 0.55)
    insight.screened_titles = screened

    # 3) 高频访问且无标记的域名：弱正证据（防「只罚不奖」偏差）
    flagged_domains = {f["domain"] for f in insight.flagged}
    for domain, n in domain_counts.items():
        if n >= 3 and domain not in flagged_domains and not _is_whitelisted(domain):
            trust = memory.set_entity_trust(domain, "domain", 0.03)
            insight.trust_updates.append({"entity": domain, "trust": round(trust, 3)})
    return insight


def render_insight(insight: BrowseInsight) -> str:
    """人类可读的浏览健康报告（插件工具输出用）。"""
    if not insight.consent_checked:
        return "⛔ " + (insight.notes[0] if insight.notes else "未授权")
    lines = [f"👁️ 浏览画像扫描：{insight.scanned_visits} 条访问 / "
             f"{insight.distinct_domains} 个域名 / 甄别 {insight.screened_titles} 条标题"]
    if insight.interests:
        top = sorted(insight.interests.items(), key=lambda kv: -kv[1])[:3]
        lines.append("  兴趣信号：" + "，".join(f"{k}={v}" for k, v in top))
    if insight.flagged:
        lines.append(f"  ⚠️ 发现 {len(insight.flagged)} 个疑似推广/投毒域名：")
        for f in insight.flagged[:5]:
            lines.append(f"    - {f['domain']} [{f['level']} {f['score']}] {f['title'][:60]}")
    else:
        lines.append("  ✅ 未发现疑似投毒域名")
    for n in insight.notes:
        lines.append(f"  · {n}")
    return "\n".join(lines)
