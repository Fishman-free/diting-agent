# -*- coding: utf-8 -*-
"""`hermes diting` CLI 子命令树（与工具共享同一批 handler，DRY）。

  hermes diting status                     内核/授权/任务一屏总览
  hermes diting seed                       重建种子知识库（幂等）
  hermes diting consent {status,grant,revoke,purge} [--scope S]
  hermes diting scan [--days N]            浏览画像扫描（需授权）
  hermes diting tasks [--status S]         长任务列表 / resume <id> / create <目标>
  hermes diting recommend <query> [--top-k N] [--category C]
  hermes diting relay doctor <url> [--api-key-env E] [--live]
  hermes diting relay fix [--config P] [--dry-run]
  hermes diting backtest                   跑回测并输出报告
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_SUB_HELP = {
    "status": "内核/授权/长任务总览",
    "seed": "重建种子知识库（幂等）",
    "consent": "浏览画像授权管理",
    "scan": "浏览画像扫描（需授权）",
    "tasks": "长任务记忆",
    "recommend": "避毒推荐",
    "relay": "中转站诊断与修复",
    "backtest": "运行 GEO 回测",
}


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


def _call(handler, args: Dict[str, Any]) -> int:
    _force_utf8()
    print(handler(args))
    return 0


def diting_command(args: argparse.Namespace) -> int:
    _force_utf8()
    sub = getattr(args, "diting_command", None)
    if not sub:
        print("usage: hermes diting {status,seed,consent,scan,tasks,recommend,relay,backtest}")
        return 2

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
        return 0

    if sub == "seed":
        from .state import get_state
        st = get_state()
        print(f"✅ 种子知识库就绪：{st.store.count()} 条 active"
              f"（本次新写入 {sum(st.seed_counts.values())}）")
        return 0

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
        payload: Dict[str, Any] = {"action": {"list": "list", "resume": "resume",
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
