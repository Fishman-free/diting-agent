# -*- coding: utf-8 -*-
"""本地浏览器历史读取（只读、拷贝快照、内部页过滤）。

Chrome/Edge 历史为 SQLite（浏览器运行时被独占锁定）→ 先拷贝到临时文件再查询。
时间戳为 Chrome 纪元（1601-01-01 起微秒）。不注入浏览器、不装扩展、不联网。
"""

from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

_CHROME_EPOCH_OFFSET = 11644473600  # 1601→1970 秒差

_SKIP_SCHEMES = ("chrome", "edge", "about", "file", "localhost", "devtools",
                 "chrome-extension", "moz-extension", "extension")


@dataclass
class VisitRecord:
    url: str
    title: str
    domain: str
    visit_time: float      # unix 秒
    browser: str           # chrome | edge

    def to_dict(self) -> Dict[str, object]:
        return {"url": self.url, "title": self.title, "domain": self.domain,
                "visit_time": self.visit_time, "browser": self.browser}


def _candidate_paths() -> Dict[str, List[Path]]:
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData/Local"))
        return {
            "chrome": [local / "Google/Chrome/User Data/Default/History",
                       local / "Google/Chrome/User Data/Profile 1/History"],
            "edge": [local / "Microsoft/Edge/User Data/Default/History",
                     local / "Microsoft/Edge/User Data/Profile 1/History"],
        }
    if system == "Darwin":
        sup = home / "Library/Application Support"
        return {
            "chrome": [sup / "Google/Chrome/Default/History"],
            "edge": [sup / "Microsoft Edge/Default/History"],
        }
    return {
        "chrome": [home / ".config/google-chrome/Default/History",
                   home / ".config/chromium/Default/History"],
        "edge": [home / ".config/microsoft-edge/Default/History"],
    }


def detect_browsers() -> Dict[str, List[str]]:
    """探测本机存在哪些浏览器历史文件（只报告路径，不读取）。"""
    found: Dict[str, List[str]] = {}
    for browser, paths in _candidate_paths().items():
        existing = [str(p) for p in paths if p.is_file()]
        if existing:
            found[browser] = existing
    return found


def read_browser_history(*, since_days: float = 7.0, browsers: Optional[List[str]] = None,
                         limit: int = 500, include_titles: bool = True) -> List[VisitRecord]:
    """读取最近 *since_days* 天的访问记录（按最近访问时间，跨浏览器合并、按时间倒序）。

    调用方**必须**先通过 ConsentManager.check("browse_history")——本函数不做授权判断，
    授权门禁统一在 profile_feed/plugin 入口执行（单一职责）。
    """
    since_unix = time.time() - since_days * 86400
    since_chrome = int((since_unix + _CHROME_EPOCH_OFFSET) * 1_000_000)
    candidates = _candidate_paths()
    out: List[VisitRecord] = []
    for browser, paths in candidates.items():
        if browsers and browser not in browsers:
            continue
        for path in paths:
            if not path.is_file():
                continue
            out.extend(_read_one(path, browser, since_chrome, include_titles))
    out.sort(key=lambda v: v.visit_time, reverse=True)
    return out[:limit]


def _read_one(path: Path, browser: str, since_chrome: int,
              include_titles: bool) -> List[VisitRecord]:
    tmp = None
    try:
        # 拷贝快照规避浏览器独占锁（拷贝瞬间的轻微不一致可接受：只读聚合用途）
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        tmp.close()
        shutil.copy2(path, tmp.name)
        conn = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        title_col = "title" if include_titles else "'' AS title"
        rows = conn.execute(
            f"SELECT url, {title_col} AS title, last_visit_time FROM urls "
            "WHERE last_visit_time > ? ORDER BY last_visit_time DESC LIMIT 2000",
            (since_chrome,)).fetchall()
        conn.close()
    except Exception:
        return []  # 锁死/损坏/无权限：跳过该文件，不打扰用户
    finally:
        if tmp:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    out: List[VisitRecord] = []
    for r in rows:
        url = (r["url"] or "").strip()
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http") or parsed.scheme in _SKIP_SCHEMES:
            continue
        domain = (parsed.hostname or "").lower()
        if not domain or domain in ("localhost", "127.0.0.1"):
            continue
        out.append(VisitRecord(
            url=url, title=(r["title"] or "").strip()[:300], domain=domain,
            visit_time=r["last_visit_time"] / 1_000_000 - _CHROME_EPOCH_OFFSET,
            browser=browser))
    return out
