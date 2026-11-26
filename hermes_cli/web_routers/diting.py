"""谛听画像与长程记忆的桌面端点（/api/diting/*）。

与 `hermes diting profile/memory` CLI 复用 plugins.diting_guard.profile_memory
的同一批 handler（DRY）：读写走内核 MemoryStore（文件锁、即时落盘、字符限额、
危险内容扫描），桌面端与 CLI 永远看到同一份数据。
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hermes_cli.web_routers._common import config_scoped_to_thread

router = APIRouter()

_TARGETS = {"memory", "user"}
_ACTIONS = {"add", "remove", "replace", "patch"}


def _target_or_400(target: Optional[str]) -> str:
    t = (target or "memory").strip().lower()
    if t not in _TARGETS:
        raise HTTPException(status_code=400, detail="target must be memory or user")
    return t


class DitingMemoryEdit(BaseModel):
    target: str = "memory"
    action: str
    content: str = ""
    old_text: str = ""
    new_text: str = ""


@router.get("/api/diting/memory")
async def get_diting_memory(target: str = "memory", profile: Optional[str] = None):
    """MEMORY.md / USER.md 的条目、用量与文件路径。"""
    t = _target_or_400(target)

    def _run() -> Any:
        from plugins.diting_guard.profile_memory import memory_data
        return memory_data(t)

    return await config_scoped_to_thread(profile, _run)


@router.post("/api/diting/memory")
async def edit_diting_memory(body: DitingMemoryEdit, profile: Optional[str] = None):
    """add/remove/replace/patch 一次修改；返回 MemoryStore 原始结果（success/error/usage）。"""
    t = _target_or_400(body.target)
    action = (body.action or "").strip().lower()
    if action not in _ACTIONS:
        raise HTTPException(status_code=400, detail="action must be add, remove, replace or patch")

    def _run() -> Any:
        from plugins.diting_guard.profile_memory import memory_edit
        return memory_edit(t, action, content=body.content,
                           old_text=body.old_text, new_text=body.new_text)

    return await config_scoped_to_thread(profile, _run)


@router.get("/api/diting/profile")
async def get_diting_profile(profile: Optional[str] = None):
    """画像聚合：USER.md + 兴趣信号 + 授权状态 + 长任务摘要（谛听内核未就绪时降级）。"""

    def _run() -> Any:
        from plugins.diting_guard.profile_memory import profile_data
        return profile_data()

    return await config_scoped_to_thread(profile, _run)
