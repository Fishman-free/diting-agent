"""用户画像（USER.md）与内置长程记忆（MEMORY.md）的共享 handler。

CLI（`hermes diting memory/profile`）与桌面端 API（/api/diting/*）复用同一批
函数（DRY）。读写底座是内核 MemoryStore：文件锁、即时落盘、字符限额、
危险内容扫描，全部沿用 `memory` 内置工具的同一套规则。

目标映射（与内核 memory 工具一致）：
  target="memory" → MEMORY.md（长程记忆：代理笔记/事实）
  target="user"   → USER.md  （用户画像：身份、偏好、长期约定）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_ACTIONS = ("add", "remove", "replace", "patch")


def _store():
    """无 agent 上下文的安全加载（gateway/Desktop/CLI 同款入口）。"""
    from tools.memory_tool import load_on_disk_store
    return load_on_disk_store()


def _file_for(target: str):
    from tools.memory_tool import get_memory_dir
    return get_memory_dir() / ("USER.md" if target == "user" else "MEMORY.md")


def _entries_of(store, target: str) -> list[str]:
    return list(store.user_entries if target == "user" else store.memory_entries)


def _limit_of(store, target: str) -> int:
    return store.user_char_limit if target == "user" else store.memory_char_limit


def _count_of(store, target: str) -> int:
    from tools.memory_tool_store import ENTRY_DELIMITER
    return len(ENTRY_DELIMITER.join(_entries_of(store, target)))


# ── 数据层（JSON 友好，桌面端 API 直接用）───────────────────────────

def memory_data(target: str = "memory") -> dict[str, Any]:
    store = _store()
    return {
        "target": target,
        "file": str(_file_for(target)),
        "enabled": store.target_enabled(target),
        "entries": _entries_of(store, target),
        "char_count": _count_of(store, target),
        "char_limit": _limit_of(store, target),
    }


def memory_edit(target: str, action: str, *, content: str = "",
                old_text: str = "", new_text: str = "") -> dict[str, Any]:
    """执行一次修改，返回 MemoryStore 的原始结果 dict（success/error/usage…）。"""
    if action not in _ACTIONS:
        return {"success": False, "error": f"未知动作 '{action}'，可选：{'/'.join(_ACTIONS)}"}
    store = _store()
    if action == "add":
        return store.add(target, content)
    if action == "remove":
        return store.remove(target, old_text)
    if action == "replace":
        return store.replace(target, old_text, content)
    return store.patch(target, old_text, new_text)


def profile_data() -> dict[str, Any]:
    """用户画像聚合：USER.md + 谛听兴趣信号 + 授权状态 + 长任务摘要。"""
    data: dict[str, Any] = {"user": memory_data("user")}
    try:
        from .state import get_state
        st = get_state()
        data["interests"] = dict(st.watcher_state.interests() or {})
        data["consent"] = {s: bool(r.granted) for s, r in st.consent.all_status().items()}
        active = st.longtask.list_tasks("active", limit=20)
        data["longtask"] = {
            "active": [{"task_id": t.task_id, "title": t.title,
                        "open_steps": list(t.open_steps)} for t in active],
            "active_count": len(active),
        }
        data["knowledge_count"] = st.store.count()
    except Exception as exc:  # 谛听内核未就绪时画像主档（USER.md）仍可用
        data["diting_error"] = str(exc)
    return data


# ── 展示层（CLI 文本渲染）───────────────────────────────────────────

def _label(target: str) -> str:
    return "用户画像 USER.md" if target == "user" else "长程记忆 MEMORY.md"


def memory_view(target: str = "memory") -> str:
    d = memory_data(target)
    lines = [f"🧠 {_label(target)}（{d['file']}）",
             f"   用量 {d['char_count']:,}/{d['char_limit']:,} 字符"
             + ("" if d["enabled"] else "（⚠️ 已在配置中停用，仅可查看）")]
    if not d["entries"]:
        lines.append("   （空——尚无条目）")
    for i, e in enumerate(d["entries"], 1):
        lines.append(f"   {i}. {e}")
    verb = "profile" if target == "user" else "memory"
    lines.append(f"💡 修改：hermes diting {verb} add|remove|replace|patch …（-h 看示例）")
    return "\n".join(lines)


def _render_edit(result: dict[str, Any], target: str) -> str:
    if result.get("success"):
        msg = result.get("message") or "已完成"
        return (f"✅ {msg}｜{_label(target)} 现有 {result.get('entry_count', '?')} 条"
                f"（用量 {result.get('usage', '?')}）")
    lines = [f"❌ {result.get('error') or result.get('message') or '修改失败'}"]
    for m in result.get("matches") or []:
        lines.append(f"   候选：{m}")
    for e in result.get("current_entries") or []:
        lines.append(f"   当前条目：{e}")
    return "\n".join(lines)


def memory_edit_view(target: str, action: str, *, content: str = "",
                     old_text: str = "", new_text: str = "") -> str:
    return _render_edit(memory_edit(target, action, content=content,
                                    old_text=old_text, new_text=new_text), target)


def profile_view() -> str:
    d = profile_data()
    lines = [memory_view("user")]
    if "diting_error" in d:
        lines.append(f"⚠️ 谛听扩展画像不可用：{d['diting_error']}")
        return "\n".join(lines)
    interests = d.get("interests") or {}
    top = sorted(interests.items(), key=lambda kv: -kv[1])[:10]
    lines.append("🔭 谛听兴趣信号（浏览画像，授权制）："
                 + ("、".join(f"{k}({v:.1f})" for k, v in top) if top else "（空）"))
    consent = d.get("consent") or {}
    lines.append("🔐 授权状态：" + "、".join(
        f"{s}={'已授权' if g else '未授权'}" for s, g in consent.items()))
    lt = d.get("longtask") or {}
    actives: Optional[list[dict[str, Any]]] = lt.get("active")
    if actives is not None:
        lines.append(f"📋 进行中长任务：{lt.get('active_count', 0)} 个")
        for t in actives[:5]:
            lines.append(f"   - [{t['task_id']}] {t['title']}（未完成步骤 {len(t['open_steps'])}）")
        lines.append("💡 长任务详情：hermes diting tasks list|resume|create|complete")
    return "\n".join(lines)
