"""`hermes diting` CLI 子命令树（与工具共享同一批 handler，DRY）。

  hermes diting status                     内核/授权/任务一屏总览
  hermes diting help                       显示全部命令与用法示例
  hermes diting seed                       重建种子知识库（幂等）
  hermes diting consent {status,grant,revoke,purge} [--scope S]
  hermes diting scan [--days N]            浏览画像扫描（需授权）
  hermes diting tasks [--status S]         长任务列表 / resume <id> / create <目标>
  hermes diting recommend <query> [--top-k N] [--category C]
  hermes diting relay doctor <url> [--api-key-env E] [--live]
  hermes diting relay fix [--config P] [--dry-run]
  hermes diting backtest                   跑回测并输出报告
  hermes diting profile {show,add,remove,replace,patch} …   用户画像（USER.md）
  hermes diting memory  {show,add,remove,replace,patch} …   长程记忆（MEMORY.md）
  hermes diting evolve <skill> [--iterations N] …           技能自进化（DSPy+GEPA）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_SUB_HELP = {
    "status": "内核/授权/长任务总览",
    "help": "显示全部命令与用法示例",
    "seed": "重建种子知识库（幂等）",
    "consent": "浏览画像授权管理",
    "scan": "浏览画像扫描（需授权）",
    "tasks": "长任务记忆",
    "recommend": "避毒推荐",
    "relay": "中转站诊断与修复",
    "backtest": "运行 GEO 回测",
    "profile": "查看/修改用户画像（USER.md + 兴趣信号）",
    "memory": "查看/修改长程记忆（MEMORY.md）",
    "evolve": "技能自进化（DSPy+GEPA，需 [evolution] extra）",
}

_EDIT_CHOICES = ["show", "add", "remove", "replace", "patch"]

_FULL_HELP = """\
谛听 Diting — 命令全览（任意命令加 -h 看详细参数）
用法：hermes diting <命令> [参数]

🛡️ 内核
  status                                  内核/授权/长任务一屏总览
  seed                                    重建种子知识库（幂等）
  backtest                                运行 GEO 回测并输出报告

🧠 用户画像与长程记忆（内置记忆，即时落盘）
  profile                                 查看用户画像：USER.md 条目 + 兴趣信号 + 授权 + 长任务
  profile add <内容>                      新增一条画像（如：偏好简体中文回复）
  profile remove <关键词>                 删除包含该关键词的条目
  profile replace <关键词> <新条目>       整条替换（关键词只用于定位）
  profile patch <关键词> <新文本>         局部改写条目中的一段
  memory                                  查看长程记忆（MEMORY.md 全部条目与用量）
  memory add|remove|replace|patch …       同上，作用于 MEMORY.md

🔐 授权与浏览画像（默认关闭，须显式授权）
  consent status|grant|revoke|purge [--scope browse_history|recommend_personalized]
  scan [--days N] [--limit N]             扫描浏览历史提取兴趣信号（需先 grant）

📋 长任务与推荐
  tasks list [--status S]                 任务列表
  tasks create <目标>                     建长任务
  tasks resume <id>                       生成续跑包（检查点+下一步）
  tasks complete <id>                     标记完成
  recommend <query> [--top-k N] [--category C]   避毒推荐

🔧 中转站
  relay doctor <url> [--api-key-env E] [--live]  体检 relay 端点
  relay fix [--config P] [--dry-run]             重写会重定向的 base_url

🧬 技能自进化（vendor 自 NousResearch/hermes-agent-self-evolution，MIT）
  evolve <技能名> [--iterations 10] [--eval-source synthetic|golden|sessiondb]
                 [--dataset-path P] [--optimizer-model M] [--eval-model M]
                 [--run-tests] [--dry-run]
  依赖安装：uv pip install -e ".[evolution]"；模型 key 仅走环境变量
  （OPENAI_API_KEY / OPENROUTER_API_KEY 等）；产物落 evolution/output/，人工评审后才可采纳
"""


def _add_edit_parser(p: argparse.ArgumentParser, what: str, examples: str) -> None:
    p.description = f"查看/修改{what}。动作：show（默认）、add、remove、replace、patch。"
    p.epilog = examples
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.add_argument("act", nargs="?", default="show", choices=_EDIT_CHOICES,
                   help="show=查看 add=新增 remove=删除 replace=整条替换 patch=局部改写")
    p.add_argument("arg1", nargs="?", default="",
                   help="add: 新条目内容；remove/replace/patch: 定位用关键词（条目内唯一子串）")
    p.add_argument("arg2", nargs="?", default="",
                   help="replace: 新条目全文；patch: 关键词段的替换文本")


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="diting_command")
    p = {name: subs.add_parser(name, help=h) for name, h in _SUB_HELP.items()}

    p["consent"].add_argument("action", nargs="?", default="status",
                              choices=["status", "grant", "revoke", "purge"])
    p["consent"].add_argument("--scope", default="browse_history",
                              choices=["browse_history", "recommend_personalized"])
    p["consent"].add_argument("--purge-data", action="store_true")

    p["scan"].add_argument("--days", type=float, default=7)
    p["scan"].add_argument("--limit", type=int, default=500)

    p["tasks"].add_argument("task_action", nargs="?", default="list",
                            choices=["list", "resume", "create", "complete"])
    p["tasks"].add_argument("target", nargs="?", default="")
    p["tasks"].add_argument("--status", default="active")

    p["recommend"].add_argument("query", nargs="?", default="")
    p["recommend"].add_argument("--top-k", type=int, default=5)
    p["recommend"].add_argument("--category", default="")

    relay_subs = p["relay"].add_subparsers(dest="relay_action")
    rd = relay_subs.add_parser("doctor", help="体检一个 relay 端点")
    rd.add_argument("url")
    rd.add_argument("--api-key", default="")
    rd.add_argument("--api-key-env", default="")
    rd.add_argument("--live", action="store_true")
    rf = relay_subs.add_parser("fix", help="重写 config.yaml 中会重定向的 base_url")
    rf.add_argument("--config", default="")
    rf.add_argument("--dry-run", action="store_true")

    _add_edit_parser(
        p["profile"], "用户画像（USER.md，另聚合谛听兴趣信号/授权/长任务）",
        "示例：\n"
        "  hermes diting profile                          查看全部画像\n"
        "  hermes diting profile add 偏好简体中文回复\n"
        "  hermes diting profile remove 偏好简体中文\n"
        "  hermes diting profile replace 偏好简体中文 偏好中文、术语保留英文\n"
        "  hermes diting profile patch 偏好中文 偏好简体中文")
    _add_edit_parser(
        p["memory"], "长程记忆（MEMORY.md，代理的持久笔记与事实）",
        "示例：\n"
        "  hermes diting memory                           查看全部记忆\n"
        "  hermes diting memory add 项目仓库在 Desktop/diting-agent\n"
        "  hermes diting memory remove 项目仓库\n"
        "  hermes diting memory replace 项目仓库 仓库已迁至新路径 X\n"
        "  hermes diting memory patch 旧路径 新路径")

    ev = p["evolve"]
    ev.description = ("用 DSPy+GEPA 进化一个技能（SKILL.md）：生成/挖掘评测集 → 变异候选 → "
                      "约束门（测试/尺寸/语义保持）→ 产物落 evolution/output/ 供人工评审，绝不直接落库。")
    ev.epilog = ("示例：\n"
                 "  hermes diting evolve github-code-review --dry-run      验证环境与技能定位\n"
                 "  hermes diting evolve arxiv --iterations 10             合成评测集进化\n"
                 "  hermes diting evolve arxiv --eval-source sessiondb     挖掘本机会话历史\n"
                 "依赖：uv pip install -e \".[evolution]\"；模型 key 仅环境变量（OPENAI_API_KEY 等）")
    ev.formatter_class = argparse.RawDescriptionHelpFormatter
    ev.add_argument("skill", help="要进化的技能名（skills/ 下的目录名）")
    ev.add_argument("--iterations", type=int, default=10, help="GEPA 迭代次数（默认 10）")
    ev.add_argument("--eval-source", default="synthetic",
                    choices=["synthetic", "golden", "sessiondb"],
                    help="评测集来源：合成 / golden 数据集 / 本机会话历史")
    ev.add_argument("--dataset-path", default=None, help="已有评测集路径（JSONL/目录）")
    ev.add_argument("--optimizer-model", default="openai/gpt-4.1", help="GEPA 反思模型")
    ev.add_argument("--eval-model", default="openai/gpt-4.1-mini", help="LLM 评审模型")
    ev.add_argument("--run-tests", action="store_true", help="以完整 pytest 作为约束门（慢）")
    ev.add_argument("--dry-run", action="store_true", help="只验证环境/技能定位，不跑优化")


def _call(handler, args: dict[str, Any]) -> int:
    _force_utf8()
    print(handler(args))
    return 0


def _edit_command(sub: str, args: argparse.Namespace) -> int:
    """profile/memory 共用的 show/add/remove/replace/patch 分派（DRY）。"""
    from .profile_memory import memory_edit_view, memory_view, profile_view
    target = "user" if sub == "profile" else "memory"
    act, a1, a2 = args.act, (args.arg1 or "").strip(), (args.arg2 or "").strip()

    if act == "show":
        print(profile_view() if sub == "profile" else memory_view(target))
        return 0
    missing = {"add": ("内容", a1), "remove": ("关键词", a1),
               "replace": ("关键词 新条目", a1 and a2), "patch": ("关键词 新文本", a1 and a2)}[act]
    if not missing[1]:
        print(f"用法：hermes diting {sub} {act} {missing[0]}（-h 看示例）")
        return 2
    payload: dict[str, Any] = {}
    if act == "add":
        payload["content"] = a1
    elif act == "remove":
        payload["old_text"] = a1
    elif act == "replace":
        payload.update(old_text=a1, content=a2)
    else:
        payload.update(old_text=a1, new_text=a2)
    print(memory_edit_view(target, act, **payload))
    return 0


def _evolve_command(args: argparse.Namespace) -> int:
    try:
        from evolution.skills.evolve_skill import evolve
    except ImportError as exc:
        print(f"❌ 自进化依赖缺失（{getattr(exc, 'name', None) or exc}）。先安装：")
        print('   uv pip install -e ".[evolution]"    # 或 pip install "dspy>=3.0" click')
        return 2
    import contextlib
    import os
    repo_root = Path(__file__).resolve().parents[2]
    if not args.dry_run and not any(
            os.environ.get(k) for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")):
        print("⚠️ 未检测到 OPENAI_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY，"
              "优化阶段可能失败（key 仅走环境变量）")
    # evolve() 的 datasets//output/ 是 cwd 相对路径 → 固定在 evolution/ 下（已 gitignore）
    with contextlib.chdir(repo_root / "evolution"):
        try:
            evolve(skill_name=args.skill, iterations=args.iterations,
                   eval_source=args.eval_source, dataset_path=args.dataset_path,
                   optimizer_model=args.optimizer_model, eval_model=args.eval_model,
                   hermes_repo=str(repo_root), run_tests=args.run_tests,
                   dry_run=args.dry_run)
        except SystemExit as exc:  # 上游用 sys.exit 报错
            return int(exc.code or 1)
    return 0


def diting_command(args: argparse.Namespace) -> int:
    _force_utf8()
    sub = getattr(args, "diting_command", None)
    if not sub:
        print(_FULL_HELP)
        return 2
    if sub == "help":
        print(_FULL_HELP)
        return 0

    if sub == "status":
        from .state import get_state
        st = get_state()
        consents = {s: ("已授权" if r.granted else "未授权")
                    for s, r in st.consent.all_status().items()}
        active = st.longtask.list_tasks("active", limit=10)
        print(f"🛡️ 谛听内核：知识库 {st.store.count()} 条 active｜"
              f"LLM 后端 {st.config.llm}")
        print(f"🔐 授权：{consents}")
        print(f"🧠 兴趣信号：{st.watcher_state.interests() or '（空）'}")
        print(f"📋 进行中长任务：{len(active)} 个")
        for t in active:
            print(f"   - [{t.task_id}] {t.title}（未完成步骤 {len(t.open_steps)}）")
        print("💡 查看全部命令：hermes diting help")
        return 0

    if sub == "seed":
        from .state import get_state
        st = get_state()
        print(f"✅ 种子知识库就绪：{st.store.count()} 条 active"
              f"（本次新写入 {sum(st.seed_counts.values())}）")
        return 0

    if sub in ("memory", "profile"):
        return _edit_command(sub, args)

    if sub == "evolve":
        return _evolve_command(args)

    if sub == "consent":
        from .tools_extra import handle_consent
        return _call(handle_consent, {"action": args.action, "scope": args.scope,
                                      "purge_data": args.purge_data})

    if sub == "scan":
        from .tools_extra import handle_browse_scan
        return _call(handle_browse_scan, {"days": args.days, "limit": args.limit})

    if sub == "tasks":
        from .tools_extra import handle_longtask
        act = args.task_action
        payload: dict[str, Any] = {"action": {"list": "list", "resume": "resume",
                                             "create": "create",
                                             "complete": "complete"}[act],
                                   "status": args.status}
        if act == "create":
            if not args.target:
                print("用法：hermes diting tasks create 「任务目标」")
                return 2
            payload["objective"] = args.target
        elif args.target:
            payload["task_id"] = args.target
        return _call(handle_longtask, payload)

    if sub == "recommend":
        from .tools_extra import handle_recommend
        return _call(handle_recommend, {"query": args.query or "推荐好物",
                                        "top_k": args.top_k,
                                        "category": args.category})

    if sub == "relay":
        action = getattr(args, "relay_action", "")
        if action == "doctor":
            import os
            from diting.relay import diagnose
            from diting.relay.doctor import render
            key = args.api_key or (os.environ.get(args.api_key_env, "")
                                   if args.api_key_env else "")
            diag = diagnose(args.url, api_key=key, live=args.live)
            print(render(diag))
            return 0 if diag.healthy else 1
        if action == "fix":
            from diting.relay.fix import find_config, scan
            try:
                report = scan(find_config(args.config), dry_run=args.dry_run)
            except FileNotFoundError as exc:
                print(f"❌ {exc}")
                return 2
            for old, new, status in report:
                print(f"  {status}: {old}" + (f" → {new}" if old != new else ""))
            return 0
        print("用法：hermes diting relay {doctor <url>,fix}")
        return 2

    if sub == "backtest":
        try:
            from diting.backtest.run import main as backtest_main
        except ImportError:
            print("❌ 回测模块未就绪（diting/backtest）")
            return 2
        return backtest_main([])

    return 2
