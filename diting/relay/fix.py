# -*- coding: utf-8 -*-
"""relay fix：扫描 hermes config.yaml，把会重定向的 base_url 重写为最终 URL。

安全设计：
- 重写前整文件备份一次（config.yaml.diting-bak）
- 只改 `base_url:` 标量行，逐行正则，不重排/不重格式化 YAML
- 解析失败（网络/证书）的 URL 原样保留，绝不写入探测失败的猜测值
- --dry-run 只报告不落盘
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import List, Tuple

from .normalize import resolve_chain

_BASE_URL_LINE = re.compile(r"""^(\s*(?:-\s+)?base_url:\s*)(['"]?)(https?://[^\s'"]+)\2(\s*(?:#.*)?)$""")


def find_config(explicit: str = "") -> Path:
    """定位 hermes config.yaml：显式路径 > $HERMES_HOME > ~/.hermes。"""
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("HERMES_HOME") or ""
    base = Path(home).expanduser() if home else Path.home() / ".hermes"
    return base / "config.yaml"


def scan(config_path: Path, *, dry_run: bool = False,
         timeout: float = 6.0) -> List[Tuple[str, str, str]]:
    """扫描并重写。返回 [(原URL, 最终URL, 状态)]，状态 ∈ fixed/ok/skipped/dry-run。"""
    if not config_path.is_file():
        raise FileNotFoundError(f"未找到配置文件：{config_path}")
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    report: List[Tuple[str, str, str]] = []
    changed = False
    for i, line in enumerate(lines):
        m = _BASE_URL_LINE.match(line.rstrip("\n"))
        if not m:
            continue
        prefix, quote, url, suffix = m.group(1), m.group(2), m.group(3), m.group(4)
        res = resolve_chain(url.rstrip("/"), timeout=timeout)
        if res.error:
            report.append((url, url, f"skipped（探测失败：{res.error[:60]}）"))
            continue
        final = res.final_url.rstrip("/")
        if not res.redirected or final == url.rstrip("/"):
            report.append((url, final, "ok（无重定向）"))
            continue
        report.append((url, final, "dry-run（将重写）" if dry_run else "fixed（已重写）"))
        if not dry_run:
            eol = "\n" if line.endswith("\n") else ""
            lines[i] = f"{prefix}{quote}{final}{quote}{suffix}{eol}"
            changed = True
    if changed:
        backup = config_path.with_suffix(config_path.suffix + ".diting-bak")
        if not backup.exists():
            shutil.copy2(config_path, backup)
        config_path.write_text("".join(lines), encoding="utf-8")
    return report
