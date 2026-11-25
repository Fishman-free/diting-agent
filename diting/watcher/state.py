# -*- coding: utf-8 -*-
"""WatcherState：浏览派生信号的独立存储（与 geo_guard 记忆分离）。

为什么不写进 geo_guard 画像：
1. geo_guard 画像键是封闭白名单（risk_aversion 等 4 个决策相关键），
   判定链路会读取它们——兴趣信号进入画像就有污染判定公正性的风险（D-08）；
2. 隐私分区：purge() 只清浏览派生数据，不动甄别记忆；
3. 兴趣信号的唯一消费方是推荐排序，单一职责。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

_EMA_ALPHA = 0.3  # 与 geo_guard 隐式画像同款平滑系数（行为一致性）

_DDL = """
CREATE TABLE IF NOT EXISTS interest_signals (
    user_id TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   REAL NOT NULL DEFAULT 0.0,
    hits    INTEGER NOT NULL DEFAULT 0,
    updated_at REAL,
    PRIMARY KEY (user_id, key)
);
"""


class WatcherState:
    def __init__(self, db_path: Optional[str] = None, user_id: str = "default"):
        if db_path:
            self.db_path = Path(db_path)
        else:
            import os
            home = os.environ.get("DITING_HOME") or os.environ.get("HERMES_HOME") or ""
            base = Path(home) / "diting" if home else Path(__file__).resolve().parent.parent / "knowledge"
            self.db_path = base / "diting.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def bump_interest(self, key: str, signal: float) -> float:
        """EMA 更新兴趣键（signal ∈ [0,1]），返回新值。"""
        signal = max(0.0, min(1.0, float(signal)))
        row = self.conn.execute(
            "SELECT value, hits FROM interest_signals WHERE user_id=? AND key=?",
            (self.user_id, key)).fetchone()
        cur = row["value"] if row else 0.0
        hits = (row["hits"] if row else 0) + 1
        new = (1 - _EMA_ALPHA) * cur + _EMA_ALPHA * signal
        self.conn.execute(
            "INSERT INTO interest_signals(user_id,key,value,hits,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id,key) DO UPDATE SET value=?, hits=?, updated_at=?",
            (self.user_id, key, new, hits, time.time(), new, hits, time.time()))
        self.conn.commit()
        return new

    def interests(self) -> Dict[str, float]:
        return {r["key"]: r["value"] for r in self.conn.execute(
            "SELECT key, value FROM interest_signals WHERE user_id=?", (self.user_id,))}

    def purge(self) -> int:
        """删除本用户全部浏览派生信号（撤销授权时调用）。"""
        cur = self.conn.execute("DELETE FROM interest_signals WHERE user_id=?", (self.user_id,))
        self.conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self.conn.close()
