# -*- coding: utf-8 -*-
"""diting_guard —— 谛听 GEO 逆向甄别 Hermes 插件。

注册 13 个工具（8 个甄别内核 + 5 个谛听扩展）、`hermes diting` CLI 子命令树、
两个会话钩子（长任务会话关联 / 中转站重定向告警）。

设计约束：
- 注册阶段零重开销：schema 为静态数据，内核在首次工具调用时懒加载（state.py）
- 所有 handler 永不抛异常，结构化错误字符串供宿主 LLM 自纠错
- 钩子只读配置与缓存，绝不在会话路径上做超过 4 秒的网络探测
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# hermes 工具名 → geo_guard 内核工具名（内核名保持与独立插件形态/MCP 演进一致）
CORE_TOOL_MAP: Dict[str, str] = {
    "geo_screen": "screen_content",
    "geo_trace": "trace_ai_answer",
    "geo_claims": "verify_claims",
    "geo_merchant": "check_influencer",
    "geo_actions": "suggest_actions",
    "geo_recall": "recall_memory",
    "geo_remember": "remember",
    "geo_feedback": "give_feedback",
}

_CORE_EMOJI = {"geo_screen": "🛡️", "geo_trace": "🔍", "geo_claims": "⚖️",
               "geo_merchant": "🧾", "geo_actions": "🧭", "geo_recall": "💭",
               "geo_remember": "📝", "geo_feedback": "🗳️"}


def _core_schemas() -> Dict[str, Dict[str, Any]]:
    """内核 schema（OpenAI function 信封 → hermes 扁平格式），纯数据无实例化。"""
    from diting.geo_guard.plugin import build_tool_schemas

    out: Dict[str, Dict[str, Any]] = {}
    for env in build_tool_schemas():
        fn = env["function"]
        out[fn["name"]] = {"name": fn["name"], "description": fn["description"],
                           "parameters": fn["parameters"]}
    return out


def _make_core_handler(internal_name: str):
    def handler(args: Dict[str, Any], **_kw) -> str:
        from .state import get_state
        try:
            result = get_state().core.dispatch(internal_name, args or {})
            return json.dumps(result, ensure_ascii=False, indent=1)
        except Exception as exc:  # noqa: BLE001 — dispatch 本身不抛，这是最后防线
            logger.exception("diting core tool %s failed", internal_name)
            return json.dumps({"error": f"internal: {str(exc)[:200]}"},
                              ensure_ascii=False)
    handler.__name__ = f"handle_{internal_name}"
    return handler


# ---------------- 会话钩子 ----------------

def _on_session_open(**kwargs: Any) -> None:
    """会话开启：关联长任务 + 中转站重定向一次性告警（只读，不阻塞）。"""
    session_id = str(kwargs.get("session_id") or "")
    # 1) 长任务：唯一进行中任务自动关联本会话（恢复时可溯源）
    try:
        from .state import get_state
        st = get_state()
        active = st.longtask.list_tasks("active", limit=2)
        if len(active) == 1 and session_id:
            st.longtask.link_session(active[0].task_id, session_id)
            logger.info("diting: 会话 %s 已关联长任务 %s（%s）",
                        session_id[:8], active[0].task_id, active[0].title)
    except Exception as exc:  # noqa: BLE001 — 钩子失败绝不影响会话
        logger.debug("diting on_session_open longtask: %s", exc)
    # 2) 中转站重定向告警：custom provider + base_url 会 301 → 提示 relay fix
    try:
        from hermes_cli.config import load_config

        model_cfg = (load_config() or {}).get("model") or {}
        base_url = str(model_cfg.get("base_url") or "").strip()
        provider = str(model_cfg.get("provider") or "").strip().lower()
        if base_url and provider in ("custom", "ollama", "vllm", ""):
            from diting.relay.normalize import cached_resolve, prime
            res = cached_resolve(base_url) or prime(base_url, timeout=4.0)
            if res.redirected:
                logger.warning(
                    "diting: model.base_url (%s) 会重定向到 %s —— 跨域重定向会丢鉴权头。"
                    "建议运行 `hermes diting relay fix` 一键修复，或手动改为最终 URL。",
                    base_url, res.final_url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("diting on_session_open relay check: %s", exc)


def _on_session_end(**kwargs: Any) -> None:
    """会话结束：为关联了本会话的进行中长任务自动打检查点（防丢进度）。"""
    session_id = str(kwargs.get("session_id") or "")
    if not session_id:
        return
    try:
        from .state import get_state
        st = get_state()
        for t in st.longtask.list_tasks("active", limit=20):
            if session_id in t.session_ids:
                st.longtask.checkpoint(t.task_id, f"会话 {session_id[:8]} 结束（自动检查点）")
    except Exception as exc:  # noqa: BLE001
        logger.debug("diting on_session_end auto-checkpoint: %s", exc)


# ---------------- 注册入口 ----------------

def register(ctx) -> None:
    """hermes 插件加载入口：工具 + CLI + 钩子。"""
    try:
        schemas = _core_schemas()
    except Exception as exc:  # noqa: BLE001 — numpy 缺失等环境问题时优雅降级
        logger.warning("diting_guard: 内核 schema 加载失败，插件未注册（%s）", exc)
        return

    for hermes_name, internal in CORE_TOOL_MAP.items():
        schema = dict(schemas[internal])
        schema["name"] = hermes_name
        ctx.register_tool(name=hermes_name, toolset="diting_guard", schema=schema,
                          handler=_make_core_handler(internal),
                          emoji=_CORE_EMOJI.get(hermes_name, "🛡️"))

    from .tools_extra import EXTRA_TOOLS
    for name, schema, handler, emoji in EXTRA_TOOLS:
        ctx.register_tool(name=name, toolset="diting_guard", schema=schema,
                          handler=handler, emoji=emoji)

    from .cli import diting_command, register_cli
    ctx.register_cli_command(
        name="diting", help="谛听：GEO 甄别 / 避毒推荐 / 长任务 / 浏览授权 / 中转站诊断",
        setup_fn=register_cli, handler_fn=diting_command,
        description="GEO 逆向甄别内核工具箱（甄别/回溯/推荐/长任务/授权/relay doctor）")

    ctx.register_hook("on_session_open", _on_session_open)
    ctx.register_hook("on_session_end", _on_session_end)
    logger.info("diting_guard: 已注册 %d 工具 + diting CLI + 2 会话钩子",
                len(CORE_TOOL_MAP) + len(EXTRA_TOOLS))
