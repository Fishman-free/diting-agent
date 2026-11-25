# -*- coding: utf-8 -*-
"""SafeRecommender：内容相似 + 协同信号 + GEO 安全门的混合推荐。

评分公式（全部可解释，每一项都能在 explanation 里找到出处）：
  relevance = 0.55×内容相似(查询/画像向量)
            + 0.30×协同信号(item-item 共现余弦)
            + 0.15×品类兴趣加成(画像 interest_*)
            + 人气小项(交互加权计数，冷启动兜底，封顶 0.1)
  final     = relevance × (1 − penalty)          # penalty 由安全门累加，封顶 0.95
  excluded  = 安全门判定 HIGH 的候选 → final=0，保留在结果尾部并给出剔除理由

协同信号借用 implicit/RecBole 的 item-item 隐式反馈模式，但用共现计数余弦
代替 ALS——单机个人数据量级下免编译依赖、确定性可复现（KISS）。
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..geo_guard.detection.comments import CommentItem
from ..geo_guard.kb.bm25 import tokenize
from .catalog import Item, load_catalog

_DDL = """
CREATE TABLE IF NOT EXISTS interactions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    kind    TEXT NOT NULL,             -- view|like|buy|screen|dismiss
    session TEXT DEFAULT '',
    ts      REAL
);
CREATE INDEX IF NOT EXISTS idx_int_user ON interactions(user_id, ts);
"""

_KIND_WEIGHT = {"view": 1.0, "screen": 1.0, "like": 3.0, "buy": 4.0, "dismiss": -2.0}


@dataclass
class SafetyVerdict:
    """单个候选的安全门结论（可解释性是硬要求）。"""

    penalty: float = 0.0
    excluded: bool = False
    flags: List[str] = field(default_factory=list)      # fake_reviews|bad_merchant|risk_copy|distrust
    reasons: List[str] = field(default_factory=list)    # 人类可读理由
    suspicious_ratio: float = 0.0
    screen_level: str = ""


@dataclass
class RecommendEntry:
    item: Item
    relevance: float
    penalty: float
    final_score: float
    excluded: bool
    safety: SafetyVerdict
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item.item_id, "title": self.item.title,
            "category": self.item.category, "merchant": self.item.merchant,
            "price": self.item.price,
            "relevance": round(self.relevance, 4),
            "penalty": round(self.penalty, 3),
            "final_score": round(self.final_score, 4),
            "excluded": self.excluded,
            "flags": self.safety.flags, "reasons": self.safety.reasons,
            "suspicious_ratio": round(self.safety.suspicious_ratio, 3),
            "screen_level": self.safety.screen_level,
            "explanation": self.explanation,
        }


@dataclass
class RecommendResult:
    query: str
    entries: List[RecommendEntry] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def kept(self) -> List[RecommendEntry]:
        return [e for e in self.entries if not e.excluded]

    @property
    def blocked(self) -> List[RecommendEntry]:
        return [e for e in self.entries if e.excluded]

    def to_dict(self) -> Dict[str, Any]:
        return {"query": self.query,
                "items": [e.to_dict() for e in self.entries],
                "notes": self.notes}


def _default_db() -> Path:
    home = os.environ.get("DITING_HOME") or os.environ.get("HERMES_HOME") or ""
    base = Path(home) / "diting" if home else Path(__file__).resolve().parent.parent / "knowledge"
    base.mkdir(parents=True, exist_ok=True)
    return base / "recommend.db"


class SafeRecommender:
    def __init__(self, guard, memory, *, catalog: Optional[Sequence[Item]] = None,
                 catalog_path: Optional[str] = None, db_path: Optional[str] = None,
                 user_id: str = "default"):
        self.guard = guard                      # GeoGuard 门面（甄别/评论/商家核查）
        self.memory = memory                    # MemoryStore（画像/实体信任）
        self.user_id = user_id
        self.items: List[Item] = list(catalog) if catalog is not None else load_catalog(catalog_path)
        self._index = {it.item_id: i for i, it in enumerate(self.items)}
        self._vecs = self._build_vectors()
        self._idf_cache: Dict[str, float] = {}
        db = Path(db_path) if db_path else _default_db()
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()
        self._safety_cache: Dict[str, SafetyVerdict] = {}

    # ---------------- 向量 ----------------

    def _build_vectors(self) -> np.ndarray:
        """TF-IDF（子线性 tf）+ L2 归一化；分词复用 geo_guard 的中文 bigram。"""
        docs = [tokenize(it.index_text) for it in self.items]
        df: Counter = Counter()
        for toks in docs:
            df.update(set(toks))
        n = max(1, len(docs))
        vecs = np.zeros((n, max(1, len(df))), dtype=np.float32)
        vocab = {t: i for i, t in enumerate(sorted(df))}
        self._idf_cache = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        for r, toks in enumerate(docs):
            tf: Counter = Counter(toks)
            for t, c in tf.items():
                vecs[r, vocab[t]] = (1 + math.log(c)) * self._idf_cache.get(t, 1.0)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms

    def _embed_query(self, text: str) -> np.ndarray:
        toks = tokenize(text)
        vec = np.zeros(self._vecs.shape[1], dtype=np.float32)
        tf: Counter = Counter(toks)
        # 查询词可能不在目录词表：用列对齐重建（vocab 与 _build_vectors 相同排序）
        vocab = self._vocab()
        for t, c in tf.items():
            j = vocab.get(t)
            if j is not None:
                vec[j] = (1 + math.log(c)) * self._idf_cache.get(t, 1.0)
        n = np.linalg.norm(vec)
        return vec / n if n else vec

    _vocab_cache: Optional[Dict[str, int]] = None

    def _vocab(self) -> Dict[str, int]:
        if self._vocab_cache is None:
            df: Counter = Counter()
            for it in self.items:
                df.update(set(tokenize(it.index_text)))
            self._vocab_cache = {t: i for i, t in enumerate(sorted(df))}
        return self._vocab_cache

    # ---------------- 交互日志与协同信号 ----------------

    def record_interaction(self, item_id: str, kind: str = "view",
                           session: str = "") -> None:
        if item_id not in self._index:
            raise KeyError(f"目录中不存在: {item_id}")
        if kind not in _KIND_WEIGHT:
            raise ValueError(f"未知交互类型: {kind}（可选 {sorted(_KIND_WEIGHT)}）")
        self.conn.execute(
            "INSERT INTO interactions(user_id,item_id,kind,session,ts) VALUES(?,?,?,?,?)",
            (self.user_id, item_id, kind, session, time.time()))
        self.conn.commit()

    def _interactions(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT item_id,kind,session,ts FROM interactions WHERE user_id=? ORDER BY ts",
            (self.user_id,)).fetchall()

    def _positive_set(self) -> set:
        return {r["item_id"] for r in self._interactions()
                if r["kind"] in ("like", "buy")}

    def _popularity(self) -> Dict[str, float]:
        pop: Counter = Counter()
        for r in self._interactions():
            pop[r["item_id"]] += _KIND_WEIGHT.get(r["kind"], 0.0)
        m = max(pop.values()) if pop else 0.0
        return {k: (v / m if m > 0 else 0.0) for k, v in pop.items()}

    def _cooc_scores(self) -> Dict[str, float]:
        """item-item 共现：与正反馈项同 session（或 30 分钟窗口）出现的项得分。"""
        pos = self._positive_set()
        if not pos:
            return {}
        rows = self._interactions()
        sessions: Dict[str, List[str]] = defaultdict(list)
        for i, r in enumerate(rows):
            key = r["session"] or f"win-{int(r['ts'] // 1800)}"
            sessions[key].append(r["item_id"])
        cooc: Counter = Counter()
        for ids in sessions.values():
            uniq = set(ids)
            if not (uniq & pos):
                continue
            for it in uniq:
                if it not in pos:
                    cooc[it] += sum(1 for p in uniq & pos)
        m = max(cooc.values()) if cooc else 0.0
        return {k: v / m for k, v in cooc.items()} if m else {}

    def _profile_vector(self) -> Optional[np.ndarray]:
        pos = self._positive_set()
        if not pos:
            return None
        rows = [self._vecs[self._index[i]] for i in pos if i in self._index]
        if not rows:
            return None
        v = np.mean(rows, axis=0)
        n = np.linalg.norm(v)
        return v / n if n else None

    # ---------------- GEO 安全门 ----------------

    def safety_gate(self, item: Item) -> SafetyVerdict:
        """四道毒检：虚假评论 → 恶意商家 → 实体信任 → 违规文案。结果按 item 缓存。"""
        if item.item_id in self._safety_cache:
            return self._safety_cache[item.item_id]
        v = SafetyVerdict()

        # ① 虚假评论/刷屏水军（≥5 条才有统计意义，与 CommentAnalyzer 阈值一致）
        if len(item.reviews) >= 5:
            items = [CommentItem(text=str(r.get("text", "")),
                                 author=str(r.get("author", "")),
                                 created_at=str(r.get("created_at", "")))
                     for r in item.reviews]
            ca = self.guard.comments.analyze(items)
            v.suspicious_ratio = ca.suspicious_ratio
            if ca.suspicious_ratio >= 0.3:
                v.penalty += 0.45
                v.flags.append("fake_reviews")
                v.reasons.append(
                    f"评论区检测到刷屏/模板化好评（可疑占比 {ca.suspicious_ratio:.0%}，"
                    f"近重复聚簇 {ca.duplicate_clusters} 个、同分钟聚簇 {ca.time_clusters} 个）")
            if ca.negative_ratio >= 0.4 and ca.valid_total >= 5:
                v.penalty += 0.2
                v.flags.append("negative_reviews")
                v.reasons.append(f"有效负评占比偏高（{ca.negative_ratio:.0%}）")
            if ca.lei_points:
                v.reasons.append("评论雷点词：" + "、".join(ca.lei_points[:4]))

        # ② 恶意商家（KB4 历史记录）
        if item.merchant:
            inf = self.guard.check_influencer(item.merchant)
            if inf.get("found"):
                credit = inf.get("credit_score")
                if credit is not None and float(credit) < 0.45:
                    v.penalty += 0.55
                    v.flags.append("bad_merchant")
                    rec = (inf.get("records") or [{}])[0].get("title", "")
                    v.reasons.append(f"商家「{item.merchant}」有历史违规记录（信用分 {credit}）：{rec}")
                else:
                    v.reasons.append(f"商家「{item.merchant}」在案例库有记录，信用分 {credit}（未达降权阈值）")

        # ③ 记忆层实体信任（watcher/甄别历史积累的负信任）
        try:
            trust = self.memory.get_profile().entity_trust.get(item.merchant or item.item_id)
            if trust is not None and trust < -0.2:
                v.penalty += 0.15
                v.flags.append("distrust")
                v.reasons.append(f"历史交互信任度为负（{trust:.2f}）")
        except Exception:
            pass

        # ④ 违规宣传文案（标题+描述过甄别；screen_content 自带缓存）
        report = self.guard.screen_content(f"{item.title}\n{item.description}")
        v.screen_level = report.level.value
        t_high = float(getattr(self.guard.config, "t_high", 0.72))
        contradicted = [c.text for c in report.claims if c.verdict == "contradicted"]
        if report.level.value == "high":
            v.excluded = True
            v.penalty = max(v.penalty, 0.95)
            v.flags.append("risk_copy_high")
            labels = [e.label for e in report.evidence[:3]]
            v.reasons.append(f"宣传文案高风险（{report.score:.2f}）：{'；'.join(labels) or '规则兜底命中'}")
        elif report.level.value == "medium" and report.score >= t_high:
            # 推荐场景保守策略：分数已达高风险线、仅因证据单薄降档的候选照样剔除。
            # 甄别的「单信号禁否决」保护的是对内容的公正判定；推荐是主动供给行为，
            # 宁可少推不可推毒（两条原则各自成立，互不冲突）。
            v.excluded = True
            v.penalty = max(v.penalty, 0.95)
            v.flags.append("risk_copy_conservative")
            extra = f"，与权威事实矛盾：{'；'.join(t[:40] for t in contradicted[:2])}" if contradicted else ""
            v.reasons.append(
                f"宣传文案风险分 {report.score:.2f} 已达高风险线（证据单薄降档为 medium），"
                f"推荐场景保守剔除{extra}")
        elif report.level.value == "medium":
            v.penalty += 0.35
            v.flags.append("risk_copy")
            labels = [e.label for e in report.evidence[:3]]
            v.reasons.append(f"宣传文案含违规话术（{report.score:.2f}）：{'；'.join(labels)}")

        v.penalty = min(0.95, v.penalty)
        self._safety_cache[item.item_id] = v
        return v

    # ---------------- 推荐 ----------------

    def recommend(self, query: str = "", category: str = "", top_k: int = 5,
                  include_blocked: bool = True,
                  interests: Optional[Dict[str, float]] = None) -> RecommendResult:
        """interests：品类兴趣加成（watcher.WatcherState.interests()），None 则不加成。"""
        result = RecommendResult(query=query)
        if not self.items:
            result.notes.append("目录为空")
            return result
        interests = interests or {}

        qv = self._embed_query(query) if query.strip() else None
        pv = self._profile_vector()
        cooc = self._cooc_scores()
        pop = self._popularity()
        if qv is None and pv is None:
            result.notes.append("冷启动：无查询且无历史正反馈，按品类兴趣+人气排序")

        entries: List[RecommendEntry] = []
        for it in self.items:
            if category and category not in (it.category, it.interest_key):
                continue
            # 内容相似：查询向量优先，其次画像向量
            if qv is not None:
                content = float(self._vecs[self._index[it.item_id]] @ qv)
            elif pv is not None:
                content = float(self._vecs[self._index[it.item_id]] @ pv)
            else:
                content = 0.0
            interest = float(interests.get(it.interest_key, 0.0)) if it.interest_key else 0.0
            relevance = (0.55 * max(0.0, content)
                         + 0.30 * cooc.get(it.item_id, 0.0)
                         + 0.15 * interest
                         + 0.10 * pop.get(it.item_id, 0.0))
            sv = self.safety_gate(it)
            final = 0.0 if sv.excluded else relevance * (1 - sv.penalty)
            why = self._explain(it, relevance, sv, content, interest)
            entries.append(RecommendEntry(item=it, relevance=relevance,
                                          penalty=sv.penalty, final_score=final,
                                          excluded=sv.excluded, safety=sv,
                                          explanation=why))
        entries.sort(key=lambda e: (e.excluded, -e.final_score))
        if query.strip():
            # 有查询时只保留真正相关的候选：不相关 ≠ 推荐（无关项混入会稀释信任）
            relevant = [e for e in entries if not e.excluded and e.relevance >= 0.05]
            if not relevant and any(e.excluded and e.relevance >= 0.05 for e in entries):
                result.notes.append("唯一相关的候选被安全门剔除——宁可不推，不推毒")
            keep = relevant[:top_k]
        else:
            keep = [e for e in entries if not e.excluded][:top_k]
        blocked = [e for e in entries if e.excluded and e.relevance >= 0.05] \
            if query.strip() else [e for e in entries if e.excluded]
        result.entries = keep + (blocked if include_blocked else [])
        if blocked:
            result.notes.append(f"{len(blocked)} 个候选被安全门剔除（保留在结果尾部，附剔除理由）")
        return result

    @staticmethod
    def _explain(it: Item, relevance: float, sv: SafetyVerdict,
                 content: float, interest: float) -> str:
        parts = [f"相关性 {relevance:.2f}（内容 {content:.2f} / 兴趣 {interest:.2f}）"]
        if sv.excluded:
            parts.append("已剔除：" + "；".join(sv.reasons[:2]))
        elif sv.penalty > 0:
            parts.append(f"降权 {sv.penalty:.0%}：" + "；".join(sv.reasons[:2]))
        else:
            parts.append("安全检查通过（无刷屏评论/无商家违规记录/文案合规）")
        return "｜".join(parts)

    def close(self) -> None:
        self.conn.close()


def render_result(res: RecommendResult, *, max_items: int = 5) -> str:
    lines = [f"🎯 避毒推荐（查询：{res.query or '（画像驱动）'}）"]
    for e in res.entries[:max_items + 3]:
        mark = "⛔" if e.excluded else ("⚠️" if e.penalty >= 0.3 else "✅")
        price = f" ¥{e.item.price:.0f}" if e.item.price else ""
        lines.append(f"  {mark} [{e.final_score:.2f}] {e.item.title}{price}（{e.item.merchant}）")
        lines.append(f"      {e.explanation}")
    for n in res.notes:
        lines.append(f"  · {n}")
    return "\n".join(lines)
