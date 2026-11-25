# -*- coding: utf-8 -*-
"""relay CLI：python -m diting.relay {doctor,fix} ..."""

from __future__ import annotations

import argparse
import json
import sys

from .doctor import diagnose, render
from .fix import find_config, scan


def _force_utf8_stdout() -> None:
    """Windows GBK 控制台兜底：emoji/中文报告统一 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="diting.relay", description="谛听中转站诊断与修复")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_doc = sub.add_parser("doctor", help="体检一个 OpenAI 兼容 relay 端点")
    p_doc.add_argument("url", help="base_url，如 https://micuapi.ai/v1")
    p_doc.add_argument("--api-key", default="", help="可选：做鉴权探测（仅本机使用）")
    p_doc.add_argument("--live", action="store_true", help="发一条最小 chat 请求实测")
    p_doc.add_argument("--json", action="store_true", help="输出 JSON")

    p_fix = sub.add_parser("fix", help="扫描 config.yaml，重写会重定向的 base_url")
    p_fix.add_argument("--config", default="", help="配置文件路径（默认 $HERMES_HOME/config.yaml）")
    p_fix.add_argument("--dry-run", action="store_true", help="只报告不落盘")

    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        diag = diagnose(args.url, api_key=args.api_key, live=args.live)
        if args.json:
            print(json.dumps(diag.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render(diag))
        return 0 if diag.healthy else 1

    if args.cmd == "fix":
        cfg = find_config(args.config)
        try:
            report = scan(cfg, dry_run=args.dry_run)
        except FileNotFoundError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if not report:
            print(f"（{cfg} 中没有 base_url 配置项，无需修复）")
            return 0
        for old, new, status in report:
            if old != new:
                print(f"  {status}: {old} → {new}")
            else:
                print(f"  {status}: {old}")
        fixed = sum(1 for _, _, s in report if s.startswith(("fixed", "dry-run")))
        print(f"\n共 {len(report)} 项，{fixed} 项{'待重写（dry-run）' if args.dry_run else '已重写'}。")
        if fixed:
            print("提示：备份在 config.yaml.diting-bak；重启 hermes/diting 生效。")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
