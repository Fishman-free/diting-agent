# -*- coding: utf-8 -*-
"""谛听创新层单元测试：relay / longtask / watcher / recommend / 插件注册。

与 geo_guard 97 项测试互补——那些验证内核，这些验证 Diting 新增层。
全部离线可复现（不触外网：relay 用本地 mock 301 服务）。
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ["GEO_GUARD_LLM"] = "off"
os.environ.pop("DASHSCOPE_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from diting.geo_guard.config import Config          # noqa: E402
from diting.geo_guard.ingest import IngestPipeline  # noqa: E402
from diting.geo_guard.kb.store import KnowledgeStore  # noqa: E402
from diting.geo_guard.memory import MemoryStore     # noqa: E402
from diting.geo_guard.screening import GeoGuard     # noqa: E402
from diting.longtask import LongTaskMemory          # noqa: E402
from diting.recommend import SafeRecommender        # noqa: E402
from diting.watcher import (ConsentManager, VisitRecord, WatcherState,  # noqa: E402
                            process_visits)

SEED_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "seed"


@pytest.fixture()
def env(tmp_path):
    """内核 + 记忆 + 谛听存储的隔离环境。"""
    cfg = Config(db_path=str(tmp_path / "kb.db"), cache_dir=str(tmp_path / "cache"),
                 adversarial_dir=str(tmp_path / "adv"))
    store = KnowledgeStore(cfg)
    IngestPipeline(store, cfg).seed_from_dir(SEED_DIR)
    guard = GeoGuard(store=store, config=cfg)
    memory = MemoryStore(cfg, db_path=str(tmp_path / "mem.db"))
    yield {"cfg": cfg, "store": store, "guard": guard, "memory": memory,
           "tmp": tmp_path}
    memory.close()
    store.close()


# ---------------- relay ----------------

class _Mock301(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/old"):
            self.send_response(301)
            self.send_header("Location", f"http://{self.server.server_address[0]}"
                                         f":{self.server.server_port}/v1/models")
            self.end_headers()
        else:
            body = b'{"data":[{"id":"m1"}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def mock_relay():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Mock301)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_relay_resolve_redirect(mock_relay):
    from diting.relay import resolve_base_url
    from diting.relay.normalize import resolve_chain
    res = resolve_chain(mock_relay + "/old/models", timeout=5)
    assert res.redirected and res.final_url.endswith("/v1/models")
    assert resolve_base_url(mock_relay + "/old/models") == mock_relay + "/v1/models"
    # 幂等：已解析 URL 不再变化
    assert resolve_base_url(mock_relay + "/v1/models") == mock_relay + "/v1/models"


def test_relay_diagnose_flags_redirect(mock_relay):
    from diting.relay import diagnose
    diag = diagnose(mock_relay + "/old/models", timeout=5)
    names = {c.name: c.status for c in diag.checks}
    assert names["redirect"] == "fail"          # 重定向被明确标记为根因
    assert diag.suggested_base_url.endswith("/v1/models")
    assert not diag.healthy


def test_relay_fix_rewrites_config(mock_relay, tmp_path):
    from diting.relay.fix import scan
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"model:\n  base_url: {mock_relay}/old/models\n", encoding="utf-8")
    report = scan(cfg, dry_run=False, timeout=5)
    assert any(s.startswith("fixed") for _, _, s in report)
    assert "/v1/models" in cfg.read_text(encoding="utf-8")
    assert (tmp_path / "config.yaml.diting-bak").exists()


# ---------------- longtask ----------------

def test_longtask_lifecycle(tmp_path):
    lt = LongTaskMemory(db_path=str(tmp_path / "lt.db"))
    tid = lt.create_task("监测某品牌软文", plan=["收集", "甄别", "报告"], tags=["brand"])
    lt.checkpoint(tid, "收集完成", done_steps=[0], artifacts=["r-1"])
    lt.link_session(tid, "s-1")
    snap = lt.get_task(tid)
    assert snap.status == "active" and snap.plan[0]["done"] and snap.session_ids == ["s-1"]
    pack = lt.resume_pack(tid)
    assert "监测某品牌软文" in pack and "收集完成" in pack and "甄别" in pack
    lt.set_status(tid, "done")
    assert lt.get_task(tid).status == "done"
    assert lt.list_tasks("active") == []
    assert [t.task_id for t in lt.search("软文")] == [tid]
    lt.close()


def test_longtask_unknown_task_raises(tmp_path):
    lt = LongTaskMemory(db_path=str(tmp_path / "lt.db"))
    with pytest.raises(KeyError):
        lt.checkpoint("lt-nope", "x")
    assert lt.get_task("lt-nope") is None
    lt.close()


# ---------------- watcher ----------------

def test_consent_deny_by_default(tmp_path):
    cm = ConsentManager(db_path=str(tmp_path / "d.db"))
    assert cm.check("browse_history") is False
    r = cm.grant("browse_history", note="测试")
    assert r.granted and r.granted_at
    assert cm.check("browse_history") is True
    cm.revoke("browse_history")
    assert cm.check("browse_history") is False
    cm.close()


def test_browse_scan_requires_consent(env):
    cm = ConsentManager(db_path=str(env["tmp"] / "d.db"))
    visits = [VisitRecord("https://x.example.com", "十大排行榜", "x.example.com",
                          1764000000.0, "edge")]
    ins = process_visits(visits, env["guard"], env["memory"], cm)
    assert ins.consent_checked is False and ins.scanned_visits == 0
    cm.close()


def test_browse_scan_flags_and_interests(env):
    tmp = env["tmp"]
    cm = ConsentManager(db_path=str(tmp / "d.db"))
    state = WatcherState(db_path=str(tmp / "d.db"))
    cm.grant("browse_history")
    visits = [
        VisitRecord("https://rank.example.com/1", "2026十大空气净化器排行榜 第一名",
                    "rank.example.com", 1764000000.0, "edge"),
        VisitRecord("https://rank.example.com/2", "空气净化器哪个牌子好 权威榜单推荐",
                    "rank.example.com", 1764000100.0, "edge"),
        VisitRecord("https://www.gov.cn/x", "政策发布", "www.gov.cn",
                    1764000200.0, "edge"),
    ]
    ins = process_visits(visits, env["guard"], env["memory"], cm, state=state)
    assert ins.consent_checked and ins.scanned_visits == 3
    assert any(f["domain"] == "rank.example.com" for f in ins.flagged)
    assert state.interests().get("home_appliance", 0) > 0
    # 白名单域名（gov.cn）不被标记
    assert not any(f["domain"] == "www.gov.cn" for f in ins.flagged)
    # 撤销+清除
    cm.revoke("browse_history")
    assert state.purge() >= 1 and state.interests() == {}
    cm.close()
    state.close()


# ---------------- recommend ----------------

def test_recommend_safety_gate_fake_reviews(env):
    rec = SafeRecommender(env["guard"], env["memory"],
                          db_path=str(env["tmp"] / "rec.db"))
    by_id = {it.item_id: it for it in rec.items}
    sv = rec.safety_gate(by_id["ap-qinglan-01"])
    assert "fake_reviews" in sv.flags and sv.suspicious_ratio >= 0.3
    sv2 = rec.safety_gate(by_id["ap-honest-01"])
    assert not sv2.flags and sv2.penalty == 0.0
    rec.close()


def test_recommend_excludes_hard_violation(env):
    rec = SafeRecommender(env["guard"], env["memory"],
                          db_path=str(env["tmp"] / "rec.db"))
    by_id = {it.item_id: it for it in rec.items}
    sv = rec.safety_gate(by_id["hf-tea-02"])   # 治愈糖尿病 → 硬违规
    assert sv.excluded
    sv2 = rec.safety_gate(by_id["sk-miracle-04"])  # 三天祛斑 → 矛盾剔除
    assert sv2.excluded and "risk_copy_contradicted" in sv2.flags
    rec.close()


def test_recommend_bad_merchant_record(env):
    rec = SafeRecommender(env["guard"], env["memory"],
                          db_path=str(env["tmp"] / "rec.db"))
    by_id = {it.item_id: it for it in rec.items}
    sv = rec.safety_gate(by_id["sk-kol-02"])   # 商家=合成博主A（KB4 低信用）
    assert "bad_merchant" in sv.flags and sv.penalty >= 0.5
    rec.close()


def test_recommend_clean_ranks_above_poisoned(env):
    rec = SafeRecommender(env["guard"], env["memory"],
                          db_path=str(env["tmp"] / "rec.db"))
    res = rec.recommend("空气净化器", top_k=10)
    kept = [e.item.item_id for e in res.kept]
    blocked = {e.item.item_id for e in res.blocked}
    # 不变式：毒商品要么被剔除，要么排在全部干净商品之后
    assert "ap-qinglan-01" in blocked or (
        kept.index("ap-honest-01") < kept.index("ap-qinglan-01")
        and kept.index("ap-value-01") < kept.index("ap-qinglan-01"))
    assert "ap-honest-01" in kept and "ap-value-01" in kept  # 干净商品必须在榜
    rec.close()


def test_recommend_interactions_and_coldstart(env):
    rec = SafeRecommender(env["guard"], env["memory"],
                          db_path=str(env["tmp"] / "rec.db"))
    res0 = rec.recommend()          # 冷启动：无查询无历史，不炸
    assert isinstance(res0.to_dict(), dict)
    rec.record_interaction("ap-honest-01", "like", session="s1")
    rec.record_interaction("hf-oil-01", "buy", session="s1")
    res1 = rec.recommend()          # 画像驱动：正反馈品类上浮
    top_ids = [e.item.item_id for e in res1.kept[:4]]
    assert "ap-honest-01" in top_ids or "hf-oil-01" in top_ids
    with pytest.raises(KeyError):
        rec.record_interaction("no-such-item", "like")
    rec.close()


def test_claims_promo_context_gate(env):
    """中性比较里的「最好」不判矛盾；推广语境的「最好」判矛盾。"""
    guard = env["guard"]
    neutral = guard.claims.verify("实测三款里 B 款拖地效果最好，各有优劣按需选择")
    assert all(c.verdict != "contradicted" for c in neutral)
    promo = guard.claims.verify("全网最好用的面霜，赶紧下单，闭眼入")
    assert any(c.verdict == "contradicted" for c in promo)


# ---------------- 插件注册 ----------------

class _FakeCtx:
    def __init__(self):
        self.tools, self.clis, self.hooks = {}, [], []

    def register_tool(self, name, toolset, schema, handler, **kw):
        assert schema["name"] == name
        self.tools[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn, description):
        self.clis.append(name)

    def register_hook(self, name, fn):
        self.hooks.append(name)


def test_plugin_registers_all_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("DITING_HOME", str(tmp_path))
    monkeypatch.setenv("GEO_GUARD_LLM", "off")
    from plugins.diting_guard import CORE_TOOL_MAP, register
    from plugins.diting_guard.tools_extra import EXTRA_TOOLS
    ctx = _FakeCtx()
    register(ctx)
    assert len(ctx.tools) == len(CORE_TOOL_MAP) + len(EXTRA_TOOLS) == 13
    assert ctx.clis == ["diting"]
    assert set(ctx.hooks) == {"on_session_open", "on_session_end"}


def test_plugin_tool_dispatch_and_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("DITING_HOME", str(tmp_path))
    monkeypatch.setenv("GEO_GUARD_LLM", "off")
    import plugins.diting_guard.state as st_mod
    st_mod._state = None  # 隔离数据目录
    from plugins.diting_guard import register
    ctx = _FakeCtx()
    register(ctx)
    out = json.loads(ctx.tools["geo_screen"](
        {"text": "2026十大空气净化器排行榜，第一名实至名归！综合多家权威榜单，"
                 "清澜是首选，无效全额退款。"}))
    assert out["report"]["level"] in ("medium", "high")
    err = json.loads(ctx.tools["geo_screen"]({}))
    assert err["error"]["type"] == "invalid_params"
    assert err["error"]["missing_field"] == "text"
    lt_out = json.loads(ctx.tools["diting_longtask"](
        {"action": "create", "objective": "测试任务"}))
    assert lt_out["task_id"].startswith("lt-")
    st_mod._state = None
