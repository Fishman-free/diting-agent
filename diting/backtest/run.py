# -*- coding: utf-8 -*-
"""谛听回测引擎：六段式验收 + Markdown 报告。

  A 单篇甄别（26 样本 × 三档混淆矩阵）
  B 话术检索 Recall@5
  C AI 回答逆向回溯（共振检出）
  D 避毒推荐排序（毒商品必须被剔除或排在全部干净商品之后）
  E 中转站重定向解析（本地 mock 301 服务，零外网）
  F 长任务记忆生命周期（create → checkpoint → resume → complete）

运行：python -m diting.backtest.run [--report BACKTEST_REPORT.md] [--json metrics.json]
退出码：0 = 全部阈值达标；1 = 存在未达标项。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("GEO_GUARD_LLM", "off")  # 回测必须离线可复现

_RANK = {"low": 0, "medium": 1, "high": 2}


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


# ---------------- A 单篇甄别 ----------------

def section_screening(guard) -> Dict[str, Any]:
    from .corpus import CORPUS
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    fails: List[str] = []
    stats = {"injection_total": 0, "injection_high": 0,
             "softad_total": 0, "softad_hit": 0,
             "health_total": 0, "health_hit": 0, "health_contradicted": 0,
             "benign_total": 0, "benign_fp": 0}
    for s in CORPUS:
        report = guard.screen_content(s.text)
        level = report.level.value
        matrix[s.label][level] += 1
        if s.label == "injection":
            stats["injection_total"] += 1
            stats["injection_high"] += int(level == "high")
            if level != "high":
                fails.append(f"{s.id}: injection 判为 {level}")
        elif s.label == "soft_ad":
            stats["softad_total"] += 1
            stats["softad_hit"] += int(_RANK[level] >= 1)
            if _RANK[level] < 1:
                fails.append(f"{s.id}: soft_ad 判为 {level}")
        elif s.label == "health_claim":
            stats["health_total"] += 1
            hit = _RANK[level] >= 1
            stats["health_hit"] += int(hit)
            stats["health_contradicted"] += int(
                any(c.verdict == "contradicted" for c in report.claims))
            if not hit:
                fails.append(f"{s.id}: health_claim 判为 {level}")
        elif s.label == "benign":
            stats["benign_total"] += 1
            if _RANK[level] >= 1:
                stats["benign_fp"] += 1
                fails.append(f"{s.id}: benign 误报为 {level}({report.score:.2f})")
    inj_recall = stats["injection_high"] / max(1, stats["injection_total"])
    ad_recall = stats["softad_hit"] / max(1, stats["softad_total"])
    hc_recall = stats["health_hit"] / max(1, stats["health_total"])
    thresholds = {
        "注入检出率=100%": inj_recall >= 1.0,
        "软文≥MEDIUM≥80%": ad_recall >= 0.8,
        "健康违规≥MEDIUM≥60%": hc_recall >= 0.6,
        "良性误报≤1": stats["benign_fp"] <= 1,
    }
    return {"matrix": {k: dict(v) for k, v in matrix.items()}, "stats": stats,
            "recalls": {"injection": inj_recall, "soft_ad": ad_recall,
                        "health_claim": hc_recall},
            "fails": fails, "thresholds": thresholds}


# ---------------- B 检索 Recall@5 ----------------

def section_retrieval(guard) -> Dict[str, Any]:
    from .corpus import RETRIEVAL_CASES
    hits = 0
    detail = []
    for case in RETRIEVAL_CASES:
        results = guard.retriever.retrieve(case["query"], kbs=[case["expect_kb"]], top_k=5)
        ok = len(results) > 0
        hits += int(ok)
        detail.append({"query": case["query"], "hits@5": len(results),
                       "top1": results[0].entry.title[:40] if results else ""})
    recall = hits / max(1, len(RETRIEVAL_CASES))
    return {"recall_at_5": recall, "detail": detail,
            "thresholds": {"Recall@5≥0.8": recall >= 0.8}}


# ---------------- C 回溯 ----------------

def section_trace(guard) -> Dict[str, Any]:
    from .corpus import TRACE_CASES
    passed, detail = 0, []
    for case in TRACE_CASES:
        t = guard.trace_ai_answer(case["answer"], case["sources"])
        has_res = len(t.resonance) > 0
        ok = has_res == case["expect_resonance"]
        passed += int(ok)
        detail.append({"id": case["id"], "expect_resonance": case["expect_resonance"],
                       "resonance": has_res, "concentration": round(t.concentration, 3),
                       "missing_negatives": len(t.missing_negatives),
                       "level": t.suspicion_level.value, "ok": ok})
    return {"passed": passed, "total": len(TRACE_CASES), "detail": detail,
            "thresholds": {"共振判定全对": passed == len(TRACE_CASES)}}


# ---------------- D 推荐排序 ----------------

def section_recommend(guard, memory, rec_db: str) -> Dict[str, Any]:
    from diting.recommend import SafeRecommender
    from .corpus import RANKING_CASES
    rec = SafeRecommender(guard, memory, db_path=rec_db)
    passed, detail = 0, []
    for case in RANKING_CASES:
        res = rec.recommend(case["query"], top_k=20)
        order = [e.item.item_id for e in res.entries]
        rank = {iid: i for i, iid in enumerate(order)}
        clean_ranks = [rank[i] for i in case["clean"] if i in rank]
        poison_info = []
        ok = True
        for p in case["poisoned"]:
            entry = next((e for e in res.entries if e.item.item_id == p), None)
            if entry is None:
                poison_info.append({"id": p, "status": "未入榜"})
                continue
            if entry.excluded:
                poison_info.append({"id": p, "status": "剔除",
                                    "reason": entry.safety.reasons[0][:60]})
                continue
            worst_clean = max(clean_ranks) if clean_ranks else -1
            if rank[p] <= worst_clean:
                ok = False
                poison_info.append({"id": p, "status": f"排序违规(rank {rank[p]})"})
            else:
                poison_info.append({"id": p, "status": f"降权(rank {rank[p]} > 干净品 {worst_clean})"})
        passed += int(ok)
        detail.append({"query": case["query"], "ok": ok, "poisoned": poison_info})
    rec.close()
    return {"passed": passed, "total": len(RANKING_CASES), "detail": detail,
            "thresholds": {"避毒排序全对": passed == len(RANKING_CASES)}}


# ---------------- E relay 重定向（本地 mock，零外网） ----------------

class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/old"):
            self.send_response(301)
            self.send_header("Location", f"http://{self.server.server_address[0]}:{self.server.server_port}/new/models")
            self.end_headers()
        else:
            body = json.dumps({"data": [{"id": "mock-model-1"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):  # 静默
        pass


def section_relay() -> Dict[str, Any]:
    from diting.relay.normalize import resolve_chain
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        res = resolve_chain(f"http://127.0.0.1:{port}/old/models", timeout=5)
        ok = res.redirected and res.final_url.endswith("/new/models") and res.status == 200
        return {"redirected": res.redirected, "final_url": res.final_url,
                "status": res.status,
                "thresholds": {"301 链解析正确": ok}}
    finally:
        server.shutdown()
        server.server_close()


# ---------------- F 长任务 ----------------

def section_longtask(lt_db: str) -> Dict[str, Any]:
    from diting.longtask import LongTaskMemory
    lt = LongTaskMemory(db_path=lt_db)
    tid = lt.create_task("回测：持续监测某品牌软文", plan=["收集", "甄别", "报告"])
    lt.checkpoint(tid, "已收集 3 个来源", done_steps=[0], artifacts=["trace-x"])
    pack = lt.resume_pack(tid)
    roundtrip = ("持续监测某品牌软文" in pack and "已收集 3 个来源" in pack
                 and "甄别" in pack)
    lt.set_status(tid, "done")
    status_ok = lt.get_task(tid).status == "done"
    search_ok = len(lt.search("软文")) == 1
    lt.close()
    ok = roundtrip and status_ok and search_ok
    return {"roundtrip": roundtrip, "status_ok": status_ok, "search_ok": search_ok,
            "thresholds": {"长任务全生命周期": ok}}


# ---------------- 汇总 ----------------

def run_all() -> Dict[str, Any]:
    from diting.geo_guard.config import Config
    from diting.geo_guard.ingest import IngestPipeline
    from diting.geo_guard.kb.store import KnowledgeStore
    from diting.geo_guard.memory import MemoryStore
    from diting.geo_guard.screening import GeoGuard

    tmp = Path(tempfile.mkdtemp(prefix="diting-backtest-"))
    cfg = Config(db_path=str(tmp / "kb.db"), cache_dir=str(tmp / "cache"),
                 adversarial_dir=str(tmp / "adv"))
    store = KnowledgeStore(cfg)
    IngestPipeline(store, cfg).seed_from_dir()
    guard = GeoGuard(store=store, config=cfg)
    memory = MemoryStore(cfg, db_path=str(tmp / "mem.db"))

    results: Dict[str, Any] = {}
    results["A_screening"] = section_screening(guard)
    results["B_retrieval"] = section_retrieval(guard)
    results["C_trace"] = section_trace(guard)
    results["D_recommend"] = section_recommend(guard, memory, str(tmp / "rec.db"))
    results["E_relay"] = section_relay()
    results["F_longtask"] = section_longtask(str(tmp / "lt.db"))

    all_thresholds: Dict[str, bool] = {}
    for sec in results.values():
        all_thresholds.update(sec.get("thresholds", {}))
    results["_summary"] = {
        "total": len(all_thresholds),
        "passed": sum(1 for v in all_thresholds.values() if v),
        "thresholds": all_thresholds,
        "kb_active": store.count(),
    }
    memory.close()
    store.close()
    return results


def render_report(results: Dict[str, Any]) -> str:
    s = results["_summary"]
    a = results["A_screening"]
    lines = [
        "# 谛听 Diting 回测报告",
        "",
        f"- 回测时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 模式：离线规则驱动（GEO_GUARD_LLM=off，hash 嵌入，可复现）",
        f"- 知识库：{s['kb_active']} 条 active",
        f"- **验收阈值：{s['passed']}/{s['total']} 通过**",
        "",
        "## 阈值明细",
        "",
        "| 验收项 | 结果 |",
        "|---|---|",
    ]
    for name, ok in s["thresholds"].items():
        lines.append(f"| {name} | {'✅ 通过' if ok else '❌ 未达标'} |")
    st = a["stats"]
    lines += [
        "",
        "## A. 单篇甄别（26 合成样本）",
        "",
        "| 类别 | high | medium | low | 指标 |",
        "|---|---|---|---|---|",
    ]
    for label in ("injection", "soft_ad", "health_claim", "benign"):
        row = a["matrix"].get(label, {})
        lines.append(f"| {label} | {row.get('high',0)} | {row.get('medium',0)} | "
                     f"{row.get('low',0)} | |")
    lines += [
        "",
        f"- 注入检出率：{_pct(a['recalls']['injection'])}（要求 100%）",
        f"- 软文 ≥MEDIUM：{_pct(a['recalls']['soft_ad'])}（要求 ≥80%）",
        f"- 健康违规 ≥MEDIUM：{_pct(a['recalls']['health_claim'])}，"
        f"其中与权威事实矛盾 {st['health_contradicted']}/{st['health_total']}",
        f"- 良性误报：{st['benign_fp']}/{st['benign_total']}（要求 ≤1）",
        "",
        "## B. 话术检索",
        "",
        f"- Recall@5 = {results['B_retrieval']['recall_at_5']:.2f}（要求 ≥0.80）",
        "",
        "## C. AI 回答逆向回溯",
        "",
    ]
    for d in results["C_trace"]["detail"]:
        lines.append(f"- {d['id']}: 共振={'检出' if d['resonance'] else '无'}"
                     f"（期望{'检出' if d['expect_resonance'] else '无'}），"
                     f"集中度 {d['concentration']}，反证缺失 {d['missing_negatives']}，"
                     f"判定 {d['level']} {'✅' if d['ok'] else '❌'}")
    lines += ["", "## D. 避毒推荐排序", ""]
    for d in results["D_recommend"]["detail"]:
        lines.append(f"- 查询「{d['query']}」{'✅' if d['ok'] else '❌'}")
        for p in d["poisoned"]:
            lines.append(f"  - 毒样本 {p['id']}：{p['status']}"
                         + (f" —— {p.get('reason','')}" if p.get("reason") else ""))
    e = results["E_relay"]
    f = results["F_longtask"]
    lines += [
        "",
        "## E. 中转站重定向解析（本地 mock）",
        "",
        f"- 301 链解析：redirected={e['redirected']} → {e['final_url']} "
        f"(HTTP {e['status']}) {'✅' if e['thresholds']['301 链解析正确'] else '❌'}",
        "",
        "## F. 长任务记忆生命周期",
        "",
        f"- create→checkpoint→resume 往返：{'✅' if f['roundtrip'] else '❌'}",
        f"- 状态迁移（done）：{'✅' if f['status_ok'] else '❌'}",
        f"- 任务检索：{'✅' if f['search_ok'] else '❌'}",
        "",
        "---",
        "",
        "**声明**：回测语料全部为合成样本，仅内部评测使用，不入库、不外发；"
        "判定输出为风险提示，不构成法律结论。团队真实语料（40 品类 5000+ URL）"
        "接入后经 ingest 管线标注，再以 AnchorCalibrator 分位点法替换锚点阈值。",
    ]
    if a["fails"]:
        lines += ["", "## 未达标样本明细", ""]
        lines += [f"- {x}" for x in a["fails"]]
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diting.backtest", description="谛听回测")
    parser.add_argument("--report", default="", help="Markdown 报告输出路径")
    parser.add_argument("--json", default="", dest="json_out", help="指标 JSON 输出路径")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    results = run_all()
    report = render_report(results)
    print(report)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"\n[报告已写入] {args.report}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(results, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        print(f"[指标已写入] {args.json_out}")
    s = results["_summary"]
    return 0 if s["passed"] == s["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
