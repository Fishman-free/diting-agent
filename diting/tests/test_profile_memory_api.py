"""桌面端画像/记忆 API（hermes_cli/web_routers/diting.py）冒烟测试。

直接驱动路由函数（asyncio.run），临时 HERMES_HOME，离线零外部依赖；
与 CLI 共用 plugins.diting_guard.profile_memory 的同一批 handler。
"""

import asyncio

import pytest


@pytest.fixture()
def tmp_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def test_memory_get_and_edit_roundtrip(tmp_home):
    from hermes_cli.web_routers.diting import DitingMemoryEdit, edit_diting_memory, get_diting_memory

    r = asyncio.run(edit_diting_memory(DitingMemoryEdit(target="memory", action="add",
                                                        content="API 写入的记忆条目")))
    assert r["success"] is True
    d = asyncio.run(get_diting_memory("memory"))
    assert d["entries"] == ["API 写入的记忆条目"]
    assert d["char_limit"] == 2200 and d["file"].endswith("MEMORY.md")

    r = asyncio.run(edit_diting_memory(DitingMemoryEdit(target="memory", action="remove",
                                                        old_text="API 写入")))
    assert r["success"] is True
    assert asyncio.run(get_diting_memory("memory"))["entries"] == []


def test_user_target_and_validation(tmp_home):
    from fastapi import HTTPException
    from hermes_cli.web_routers.diting import DitingMemoryEdit, edit_diting_memory, get_diting_memory

    r = asyncio.run(edit_diting_memory(DitingMemoryEdit(target="user", action="add",
                                                        content="偏好深色模式")))
    assert r["success"] is True
    d = asyncio.run(get_diting_memory("user"))
    assert d["file"].endswith("USER.md") and d["char_limit"] == 1375

    with pytest.raises(HTTPException):
        asyncio.run(get_diting_memory("bogus"))
    with pytest.raises(HTTPException):
        asyncio.run(edit_diting_memory(DitingMemoryEdit(target="memory", action="fly")))
    bad = asyncio.run(edit_diting_memory(DitingMemoryEdit(target="memory", action="remove",
                                                          old_text="不存在")))
    assert bad["success"] is False


def test_profile_aggregate(tmp_home):
    """画像聚合：USER.md 主档 + 谛听扩展（兴趣/授权/长任务）；内核异常时降级不抛。"""
    from hermes_cli.web_routers.diting import DitingMemoryEdit, edit_diting_memory, get_diting_profile

    asyncio.run(edit_diting_memory(DitingMemoryEdit(target="user", action="add",
                                                    content="偏好简体中文回复")))
    p = asyncio.run(get_diting_profile())
    assert any("偏好简体中文回复" in e for e in p["user"]["entries"])
    # 谛听内核就绪时给出扩展画像；未就绪时给 diting_error——两者必居其一，绝不抛异常
    assert ("interests" in p and "consent" in p and "longtask" in p) or "diting_error" in p
