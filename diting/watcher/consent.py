# -*- coding: utf-8 -*-
"""授权管理：显式 opt-in，带时间戳回执，可随时撤销。"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

SCOPES = ("browse_history", "recommend_personalized")

_DDL = """
CREATE TABLE IF NOT EXISTS consents (
    user_id    TEXT NOT NULL,
    scope      TEXT NOT NULL,
    granted    INTEGER NOT NULL DEFAULT 0,
    granted_at REAL,
    revoked_at REAL,
    note       TEXT DEFAULT '',
    PRIMARY KEY (user_id, scope)
);
"""


@dataclass
class ConsentReceipt:
    scope: str
    granted: bool
    granted_at: Optional[float]
    revoked_at: Optional[float]
    note: str = ""


class ConsentManager:
    """授权状态的唯一真相源（SQLite）。默认全关（deny-by-default）。"""

    def __init__(self, db_path: Optional[str] = None, user_id: str = "default"):
        if db_path:
            self.db_path = Path(db_path)
        else:
            home = os.environ.get("DITING_HOME") or os.environ.get("HERMES_HOME") or ""
            base = Path(home) / "diting" if home else Path(__file__).resolve().parent.parent / "knowledge"
            self.db_path = base / "diting.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def _check_scope(self, scope: str) -> None:
        if scope not in SCOPES:
            raise ValueError(f"未知授权范围: {scope}（可选 {SCOPES}）")

    def grant(self, scope: str, note: str = "") -> ConsentReceipt:
        self._check_scope(scope)
        now = time.time()
        self.conn.execute(
            "INSERT INTO consents(user_id,scope,granted,granted_at,revoked_at,note) "
            "VALUES(?,?,1,?,NULL,?) "
            "ON CONFLICT(user_id,scope) DO UPDATE SET granted=1, granted_at=?, revoked_at=NULL, note=?",
            (self.user_id, scope, now, note, now, note))
        self.conn.commit()
        return self.status(scope)

    def revoke(self, scope: str) -> ConsentReceipt:
        self._check_scope(scope)
        now = time.time()
        self.conn.execute(
            "INSERT INTO consents(user_id,scope,granted,granted_at,revoked_at,note) "
            "VALUES(?,?,0,NULL,?,'revoked') "
            "ON CONFLICT(user_id,scope) DO UPDATE SET granted=0, revoked_at=?",
            (self.user_id, scope, now, now))
        self.conn.commit()
        return self.status(scope)

    def check(self, scope: str) -> bool:
        """采集入口的统一门禁：无记录 = 未授权。"""
        self._check_scope(scope)
        row = self.conn.execute(
            "SELECT granted FROM consents WHERE user_id=? AND scope=?",
            (self.user_id, scope)).fetchone()
        return bool(row and row["granted"])

    def status(self, scope: str) -> ConsentReceipt:
        self._check_scope(scope)
        row = self.conn.execute(
            "SELECT * FROM consents WHERE user_id=? AND scope=?",
            (self.user_id, scope)).fetchone()
        if row is None:
            return ConsentReceipt(scope=scope, granted=False, granted_at=None, revoked_at=None,
                                  note="未做过授权决定（默认关闭）")
        return ConsentReceipt(scope=scope, granted=bool(row["granted"]),
                              granted_at=row["granted_at"], revoked_at=row["revoked_at"],
                              note=row["note"] or "")

    def all_status(self) -> Dict[str, ConsentReceipt]:
        return {s: self.status(s) for s in SCOPES}

    def purge(self) -> int:
        """删除本用户全部授权记录与画像痕迹的授权侧数据（浏览派生数据在 profile_feed.purge）。"""
        cur = self.conn.execute("DELETE FROM consents WHERE user_id=?", (self.user_id,))
        self.conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self.conn.close()
