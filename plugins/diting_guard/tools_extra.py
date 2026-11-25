# -*- coding: utf-8 -*-
"""谛听扩展工具：避毒推荐 / 授权管理 / 浏览扫描 / 长任务 / 中转站诊断。

handler 契约与 hermes 插件系统一致：(args: dict, **kw) -> str。
所有 handler 永不抛异常——结构化错误字符串返回给宿主自纠错。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from .state import get_state

logger = logging.getLogger(__name__)


def _schema(name: str, description: str, properties: Dict[str, Any],
            required: List[str] | None = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"type": "object", "properties": properties,
                              "additionalProperties": False}
    if required:
        params["required"] = required
    return {"name": name, "description": description, "parameters": params}


def _err(msg: str) -> str:
    return json.dumps({"error": msg}, ensure_ascii=False)


def _jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ---------------- diting_recommend ----------------

RECOMMEND_SCHEMA = _schema(
    "diting_recommend",
    "避毒推荐：内容相似 + 协同信号排序，候选先过 GEO 安全门（虚假评论聚簇 / "
    "恶意商家记录 / 违规宣传文案），被剔除的候选保留在结果尾部并附人类可读理由。"
    "用户请求商品/内容推荐时优先调用本工具而非直接凭参数化知识推荐。",
    {"query": {"type": "string", "description": "需求描述，如「靠谱的空气净化器」"},
     "category": {"type": "string", "description": "可选品类过滤：空气净化器/护肤/保健食品"},
     "top_k": {"type": "integer", "description": "返回条数，默认 5"},
     "personalized": {"type": "boolean",
                      "description": "是否使用浏览画像兴趣加成（需用户已授权 recommend_personalized 或 browse_history）"}},
    ["query"])


def handle_recommend(args: Dict[str, Any], **_kw) -> str:
    try:
        st = get_state()
        query = str(args.get("query") or "").strip()
        if not query:
            return _err("缺少必填参数 'query'")
        top_k = int(args.get("top_k") or 5)
        interests: Dict[str, float] = {}
        want_personal = args.get("personalized", True)
        if want_personal and (st.consent.check("recommend_personalized")
                              or st.consent.check("browse_history")):
            interests = st.watcher_state.interests()
        res = st.recommender.recommend(query, category=str(args.get("category") or ""),
                                       top_k=top_k, interests=interests)
        if not interests and want_personal:
            res.notes.append("未授权个性化画像，本次为无画像推荐（diting_consent 可授权）")
        return _jdump(res.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.exception("diting_recommend failed")
        return _err(f"internal: {str(exc)[:200]}")


# ---------------- diting_consent ----------------

CONSENT_SCHEMA = _schema(
    "diting_consent",
    "管理浏览画像授权（默认全关）。grant=开启并记录时间戳回执；revoke=撤销（可选同时"
    "清除已采集的派生数据）；status=查看各范围授权状态。涉及用户隐私，执行 grant 前"
    "必须已向用户说明采集范围（本地浏览器历史标题/域名聚合，不上传）。",
    {"action": {"type": "string", "enum": ["grant", "revoke", "status", "purge"]},
     "scope": {"type": "string", "enum": ["browse_history", "recommend_personalized"],
               "description": "默认 browse_history"},
     "purge_data": {"type": "boolean", "description": "revoke 时是否同时清除派生数据"},
     "note": {"type": "string", "description": "授权备注（回执留痕）"}},
    ["action"])


def handle_consent(args: Dict[str, Any], **_kw) -> str:
    try:
        st = get_state()
        action = str(args.get("action") or "").strip().lower()
        scope = str(args.get("scope") or "browse_history").strip()
        if action == "status":
            out = {s: r.__dict__ for s, r in st.consent.all_status().items()}
            out["interests"] = st.watcher_state.interests()
            return _jdump(out)
        if action == "grant":
            r = st.consent.grant(scope, note=str(args.get("note") or "对话内授权"))
            return _jdump({"granted": r.__dict__,
                           "提示": "采集仅在本地进行；revoke 可随时撤销"})
        if action == "revoke":
            r = st.consent.revoke(scope)
            purged = 0
            if args.get("purge_data") and scope == "browse_history":
                purged = st.watcher_state.purge()
            return _jdump({"revoked": r.__dict__, "purged_interest_keys": purged})
        if action == "purge":
            n = st.watcher_state.purge()
            st.consent.revoke("browse_history")
            st.consent.revoke("recommend_personalized")
            return _jdump({"purged_interest_keys": n, "consents": "已全部撤销"})
        return _err(f"未知 action: {action}（grant/revoke/status/purge）")
    except Exception as exc:  # noqa: BLE001
        return _err(f"internal: {str(exc)[:200]}")


# ---------------- diting_browse_scan ----------------

BROWSE_SCAN_SCHEMA = _schema(
    "diting_browse_scan",
    "扫描本地浏览器最近访问记录（需已授权 browse_history）：识别疑似软文/投毒域名、"
    "更新品类兴趣与域名信任度。只读聚合，不上传，不存完整历史。",
    {"days": {"type": "number", "description": "回溯天数，默认 7"},
     "limit": {"type": "integer", "description": "最多读取条数，默认 500"}},
    [])


def handle_browse_scan(args: Dict[str, Any], **_kw) -> str:
    try:
        st = get_state()
        if not st.consent.check("browse_history"):
            return _err("未授权 browse_history：请先向用户说明采集范围并经同意后用 "
                        "diting_consent(action=grant) 授权")
        from diting.watcher import read_browser_history, process_visits, render_insight
        days = float(args.get("days") or 7)
        limit = int(args.get("limit") or 500)
        visits = read_browser_history(since_days=days, limit=limit)
        insight = process_visits(visits, st.guard, st.memory, st.consent,
                                 state=st.watcher_state)
        return render_insight(insight) + "\n\n" + _jdump(insight.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.exception("browse_scan failed")
        return _err(f"internal: {str(exc)[:200]}")


# ---------------- diting_longtask ----------------

LONGTASK_SCHEMA = _schema(
    "diting_longtask",
    "长任务记忆：跨会话任务的登记/推进/恢复。用户说「持续帮我盯着…」「这个任务下周继续」"
    "时 create；每完成一个阶段 checkpoint（附产物引用）；新会话用户问「上次那个事怎么样了」"
    "时 list/resume——resume 返回可直接续接工作的恢复上下文包。",
    {"action": {"type": "string",
                "enum": ["create", "checkpoint", "list", "resume", "complete",
                         "abandon", "search"]},
     "task_id": {"type": "string"},
     "objective": {"type": "string", "description": "create：任务目标"},
     "title": {"type": "string"},
     "plan": {"type": "array", "items": {"type": "string"}, "description": "create：计划步骤"},
     "tags": {"type": "array", "items": {"type": "string"}},
     "note": {"type": "string", "description": "checkpoint：本次推进说明"},
     "done_steps": {"type": "array", "items": {"type": "integer"},
                    "description": "checkpoint：完成的计划步骤下标"},
     "artifacts": {"type": "array", "items": {"type": "string"},
                   "description": "checkpoint：产物引用（report_id/路径/URL）"},
     "query": {"type": "string", "description": "search：关键词"},
     "status": {"type": "string", "description": "list 过滤：active/paused/done/abandoned"}},
    ["action"])


def handle_longtask(args: Dict[str, Any], **_kw) -> str:
    try:
        st = get_state()
        lt = st.longtask
        action = str(args.get("action") or "").strip().lower()
        if action == "create":
            objective = str(args.get("objective") or "").strip()
            if not objective:
                return _err("create 需要 objective")
            tid = lt.create_task(objective, title=str(args.get("title") or ""),
                                 plan=[str(s) for s in (args.get("plan") or [])],
                                 tags=[str(t) for t in (args.get("tags") or [])])
            return _jdump({"task_id": tid, "status": "active",
                           "提示": "用 checkpoint 记录推进，resume 跨会话恢复"})
        tid = str(args.get("task_id") or "").strip()
        if not tid and action in ("checkpoint", "resume", "complete", "abandon"):
            active = lt.list_tasks("active", limit=1)
            if len(active) == 1:
                tid = active[0].task_id  # 唯一进行中任务可省略 id
            else:
                return _err(f"需要 task_id（当前进行中任务 {len(active)} 个，无法自动定位）")
        if action == "checkpoint":
            seq = lt.checkpoint(tid, str(args.get("note") or ""),
                                done_steps=[int(i) for i in (args.get("done_steps") or [])],
                                artifacts=[str(a) for a in (args.get("artifacts") or [])])
            return _jdump({"task_id": tid, "checkpoint_seq": seq})
        if action == "list":
            status = str(args.get("status") or "active").strip()
            tasks = lt.list_tasks(status if status != "all" else None)
            return _jdump([{"task_id": t.task_id, "title": t.title,
                            "status": t.status, "open_steps": t.open_steps}
                           for t in tasks])
        if action == "resume":
            return lt.resume_pack(tid)
        if action == "complete":
            lt.checkpoint(tid, str(args.get("note") or "任务完成"))
            lt.set_status(tid, "done")
            return _jdump({"task_id": tid, "status": "done"})
        if action == "abandon":
            lt.set_status(tid, "abandoned")
            return _jdump({"task_id": tid, "status": "abandoned"})
        if action == "search":
            q = str(args.get("query") or "").strip()
            if not q:
                return _err("search 需要 query")
            return _jdump([{"task_id": t.task_id, "title": t.title, "status": t.status}
                           for t in lt.search(q)])
        return _err(f"未知 action: {action}")
    except (KeyError, ValueError) as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("longtask failed")
        return _err(f"internal: {str(exc)[:200]}")


# ---------------- diting_relay_doctor ----------------

RELAY_SCHEMA = _schema(
    "diting_relay_doctor",
    "诊断 OpenAI 兼容中转站为什么连不上：DNS / TLS / 301 重定向（鉴权头丢失根因）/ "
    "models 端点 / relay 软件指纹，输出可直接使用的 base_url 修复建议。用户报告"
    "「中转站 401 / 模型列表为空 / 连不上」时调用。",
    {"url": {"type": "string", "description": "relay 的 base_url"},
     "api_key_env": {"type": "string",
                     "description": "可选：存放密钥的环境变量名（避免密钥经过对话）"},
     "live": {"type": "boolean", "description": "是否发一条最小 chat 请求实测"}},
    ["url"])


def handle_relay_doctor(args: Dict[str, Any], **_kw) -> str:
    try:
        import os
        from diting.relay import diagnose
        from diting.relay.doctor import render
        url = str(args.get("url") or "").strip()
        if not url:
            return _err("缺少必填参数 'url'")
        key_env = str(args.get("api_key_env") or "").strip()
        api_key = os.environ.get(key_env, "") if key_env else ""
        diag = diagnose(url, api_key=api_key, live=bool(args.get("live")))
        out = render(diag)
        if key_env and not api_key:
            out += f"\n（提示：环境变量 {key_env} 未设置，跳过了鉴权探测）"
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("relay_doctor failed")
        return _err(f"internal: {str(exc)[:200]}")


# (name, schema, handler, emoji)
EXTRA_TOOLS: List[Tuple[str, Dict[str, Any], Any, str]] = [
    ("diting_recommend", RECOMMEND_SCHEMA, handle_recommend, "🎯"),
    ("diting_consent", CONSENT_SCHEMA, handle_consent, "🔐"),
    ("diting_browse_scan", BROWSE_SCAN_SCHEMA, handle_browse_scan, "👁️"),
    ("diting_longtask", LONGTASK_SCHEMA, handle_longtask, "🧠"),
    ("diting_relay_doctor", RELAY_SCHEMA, handle_relay_doctor, "🔀"),
]
