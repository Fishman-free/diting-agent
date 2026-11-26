"""Vendor 冒烟：evolution/（self-evolution）集成 + 画像/记忆命令。

零 dspy 依赖（用 sys.modules 注入模拟缺依赖路径）；记忆读写走临时
HERMES_HOME，绝不触碰真实用户数据。
"""

import argparse
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── evolution vendor：溯源 / repo 自发现 / 缺依赖提示 ─────────────────

def test_vendor_provenance():
    """MIT 归属三处齐备：VENDOR.md（上游 SHA）、NOTICE、上游 README 原样保留。"""
    vendor_md = (REPO_ROOT / "evolution" / "VENDOR.md").read_text(encoding="utf-8")
    assert "0a929e3aa20e15cf04dc7c28492a7d41a5139125" in vendor_md
    assert "MIT" in vendor_md
    assert "hermes-agent-self-evolution" in (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert (REPO_ROOT / "evolution" / "README.upstream.md").exists()


def test_own_root_discovery(monkeypatch):
    """[diting patch #1] vendor 在 fork 内部时免环境变量自发现 repo 根。"""
    monkeypatch.delenv("HERMES_AGENT_REPO", raising=False)
    from evolution.core.config import get_hermes_agent_path
    assert get_hermes_agent_path().resolve() == REPO_ROOT


def test_evolve_missing_dep_hint(monkeypatch, capsys):
    """未装 dspy 时 evolve 给出安装提示（rc=2），不抛裸 ImportError。"""
    for mod in [m for m in sys.modules if m.startswith("evolution.")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setitem(sys.modules, "dspy", None)  # import dspy → ImportError
    from plugins.diting_guard.cli import _evolve_command
    ns = argparse.Namespace(skill="demo", iterations=10, eval_source="synthetic",
                            dataset_path=None, optimizer_model="m", eval_model="m",
                            run_tests=False, dry_run=True)
    assert _evolve_command(ns) == 2
    out = capsys.readouterr().out
    assert 'uv pip install -e ".[evolution]"' in out


# ── 画像/记忆命令：临时 HERMES_HOME 下的读写闭环 ─────────────────────

@pytest.fixture()
def tmp_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def test_memory_roundtrip(tmp_home):
    from plugins.diting_guard.profile_memory import memory_data, memory_edit, memory_view
    assert memory_edit("memory", "add", content="测试记忆条目A").get("success")
    d = memory_data("memory")
    assert d["file"].endswith("MEMORY.md")
    assert any("测试记忆条目A" in e for e in d["entries"])
    assert memory_edit("memory", "patch", old_text="条目A", new_text="条目B").get("success")
    assert any("条目B" in e for e in memory_data("memory")["entries"])
    assert memory_edit("memory", "remove", old_text="条目B").get("success")
    assert memory_data("memory")["entries"] == []
    assert "MEMORY.md" in memory_view("memory")


def test_memory_edit_validation(tmp_home):
    from plugins.diting_guard.profile_memory import memory_edit
    assert not memory_edit("memory", "fly").get("success")           # 未知动作
    assert not memory_edit("memory", "add", content="").get("success")  # 空内容
    assert not memory_edit("memory", "remove", old_text="不存在").get("success")


def test_profile_view_aggregates(tmp_home):
    """profile show = USER.md 条目 + 授权状态 +（谛听内核可用时）兴趣/长任务。"""
    from plugins.diting_guard.profile_memory import memory_edit, profile_data, profile_view
    memory_edit("user", "add", content="偏好简体中文回复")
    view = profile_view()
    assert "USER.md" in view and "偏好简体中文回复" in view and "授权状态" in view
    assert profile_data()["user"]["entries"]


def test_cli_full_help_lists_all_commands(capsys):
    """「命令的提示全部放上去」：help 输出覆盖每个子命令。"""
    from plugins.diting_guard.cli import diting_command
    assert diting_command(argparse.Namespace(diting_command="help")) == 0
    out = capsys.readouterr().out
    for kw in ("status", "seed", "backtest", "profile", "memory", "consent",
               "scan", "tasks", "recommend", "relay", "evolve"):
        assert kw in out


def test_cli_profile_edit_dispatch(tmp_home, capsys):
    """argparse → diting_command 全链路：profile add 落盘 USER.md。"""
    from plugins.diting_guard.cli import diting_command, register_cli
    parser = argparse.ArgumentParser(prog="hermes")
    register_cli(parser.add_subparsers().add_parser("diting"))
    rc = diting_command(parser.parse_args(["diting", "profile", "add", "偏好深色模式"]))
    assert rc == 0 and "✅" in capsys.readouterr().out
    assert (tmp_home / "memories" / "USER.md").exists()
