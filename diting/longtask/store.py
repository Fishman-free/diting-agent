# -*- coding: utf-8 -*-
"""LongTaskMemory：SQLite 持久化的任务登记 + 检查点 + 恢复包。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_DDL = """
CREATE TABLE IF NOT EXISTS longtasks (
    task_id    TEXT PRIMARY KEY,
    user_id    TEXT DEFAULT '',
    title      TEXT DEFAULT '',
    objective  TEXT NOT NULL,
    status     TEXT DEFAULT 'active',      -- active|paused|done|abandoned
    plan_json  TEXT DEFAULT '[]',          -- 计划步骤 [{step, done}]
    session_ids TEXT DEFAULT '[]',         -- 关联过的 hermes 会话
    tags_json  TEXT DEFAULT '[]',
    created_at REAL,
    updated_at REAL,
    last_touch REAL
);
CREATE TABLE IF NOT EXISTS longtask_checkpoints (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    seq     INTEGER NOT NULL,
    note    TEXT DEFAULT '',
    state_json TEXT DEFAULT '{}',          -- 任意可序列化推进状态
    artifacts_json TEXT DEFAULT '[]',      -- 产物引用（report_id/文件路径/URL）
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_lt_status ON longtasks(status);
CREATE INDEX IF NOT EXISTS idx_ltc_task ON longtask_checkpoints(task_id, seq);
"""

_VALID_STATUS = ("active", "paused", "done", "abandoned")


@dataclass
class TaskSnapshot:
    """任务的只读快照（get_task/resume 用）。"""

    task_id: str
    title: str
    objective: str
    status: str
    plan: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    session_ids: List[str] = field(default_factory=list)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def open_steps(self) -> List[str]:
        return [str(s.get("step", "")) for s in self.plan if not s.get("done")]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id, "title": self.title, "objective": self.objective,
            "status": self.status, "plan": self.plan, "tags": self.tags,
            "session_ids": self.session_ids, "checkpoints": self.checkpoints,
            "open_steps": self.open_steps,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


def _task_id(objective: str) -> str:
    return "lt-" + hashlib.sha256(
        f"{objective.strip()}|{time.time_ns()}".encode("utf-8")).hexdigest()[:12]


class LongTaskMemory:
    """长任务记忆存储。线程内使用；SQLite 连接每实例一个。"""

    def __init__(self, db_path: Optional[str] = None, user_id: str = "default"):
        if db_path:
            self.db_path = Path(db_path)
        else:
            import os
            home = os.environ.get("DITING_HOME") or os.environ.get("HERMES_HOME") or ""
            base = Path(home) / "diting" if home else Path(__file__).resolve().parent.parent / "knowledge"
            self.db_path = base / "longtask.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    # ---------------- 写入 ----------------

    def create_task(self, objective: str, *, title: str = "",
                    plan: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> str:
        """登记新任务。plan 为步骤文本列表 → [{step, done:False}]。返回 task_id。"""
        objective = (objective or "").strip()
        if not objective:
            raise ValueError("objective 不能为空")
        tid = _task_id(objective)
        now = time.time()
        plan_rows = [{"step": str(s), "done": False} for s in (plan or [])]
        self.conn.execute(
            "INSERT INTO longtasks(task_id,user_id,title,objective,status,plan_json,"
            "session_ids,tags_json,created_at,updated_at,last_touch) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (tid, self.user_id, title or objective[:40], objective, "active",
             json.dumps(plan_rows, ensure_ascii=False), "[]",
             json.dumps(tags or [], ensure_ascii=False), now, now, now))
        self.conn.commit()
        return tid

    def checkpoint(self, task_id: str, note: str = "", *,
                   state: Optional[Dict[str, Any]] = None,
                   artifacts: Optional[List[Any]] = None,
                   done_steps: Optional[List[int]] = None) -> int:
        """追加检查点（append-only）。done_steps 标记 plan 中完成的步骤下标。返回 seq。"""
        row = self._row(task_id)
        if row is None:
            raise KeyError(f"任务不存在: {task_id}")
        seq = self.conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 s FROM longtask_checkpoints WHERE task_id=?",
            (task_id,)).fetchone()["s"]
        now = time.time()
        self.conn.execute(
            "INSERT INTO longtask_checkpoints(task_id,seq,note,state_json,artifacts_json,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (task_id, seq, note, json.dumps(state or {}, ensure_ascii=False),
             json.dumps(artifacts or [], ensure_ascii=False), now))
        if done_steps:
            plan = json.loads(row["plan_json"] or "[]")
            for i in done_steps:
                if 0 <= i < len(plan):
                    plan[i]["done"] = True
            self.conn.execute("UPDATE longtasks SET plan_json=? WHERE task_id=?",
                              (json.dumps(plan, ensure_ascii=False), task_id))
        self.conn.execute("UPDATE longtasks SET updated_at=?, last_touch=? WHERE task_id=?",
                          (now, now, task_id))
        self.conn.commit()
        return seq

    def set_status(self, task_id: str, status: str) -> None:
        if status not in _VALID_STATUS:
            raise ValueError(f"非法状态: {status}（可选 {_VALID_STATUS}）")
        self._require(task_id)
        now = time.time()
        self.conn.execute("UPDATE longtasks SET status=?, updated_at=? WHERE task_id=?",
                          (status, now, task_id))
        self.conn.commit()

    def link_session(self, task_id: str, session_id: str) -> None:
        row = self._require(task_id)
        ids = json.loads(row["session_ids"] or "[]")
        if session_id and session_id not in ids:
            ids.append(session_id)
            self.conn.execute("UPDATE longtasks SET session_ids=? WHERE task_id=?",
                              (json.dumps(ids), task_id))
            self.conn.commit()

    # ---------------- 读取 ----------------

    def get_task(self, task_id: str, *, with_checkpoints: bool = True) -> Optional[TaskSnapshot]:
        row = self._row(task_id)
        if row is None:
            return None
        cps: List[Dict[str, Any]] = []
        if with_checkpoints:
            for c in self.conn.execute(
                    "SELECT seq,note,state_json,artifacts_json,created_at "
                    "FROM longtask_checkpoints WHERE task_id=? ORDER BY seq", (task_id,)):
                cps.append({"seq": c["seq"], "note": c["note"],
                            "state": json.loads(c["state_json"] or "{}"),
                            "artifacts": json.loads(c["artifacts_json"] or "[]"),
                            "created_at": c["created_at"]})
        return TaskSnapshot(
            task_id=row["task_id"], title=row["title"], objective=row["objective"],
            status=row["status"], plan=json.loads(row["plan_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            session_ids=json.loads(row["session_ids"] or "[]"), checkpoints=cps,
            created_at=row["created_at"], updated_at=row["updated_at"])

    def list_tasks(self, status: Optional[str] = "active", limit: int = 20) -> List[TaskSnapshot]:
        sql = "SELECT task_id FROM longtasks WHERE user_id=?"
        args: List[Any] = [self.user_id]
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY last_touch DESC LIMIT ?"
        args.append(limit)
        return [s for s in (self.get_task(r["task_id"], with_checkpoints=False)
                            for r in self.conn.execute(sql, args)) if s]

    def search(self, query: str, limit: int = 10) -> List[TaskSnapshot]:
        """在目标/标题/检查点笔记中做子串检索（KISS：任务量级小，无需 FTS）。"""
        q = (query or "").strip().lower()
        if not q:
            return []
        hits = self.conn.execute(
            "SELECT DISTINCT t.task_id FROM longtasks t "
            "LEFT JOIN longtask_checkpoints c ON c.task_id=t.task_id "
            "WHERE t.user_id=? AND (lower(t.objective) LIKE ? OR lower(t.title) LIKE ? "
            "OR lower(c.note) LIKE ?) ORDER BY t.last_touch DESC LIMIT ?",
            (self.user_id, f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()
        return [s for s in (self.get_task(h["task_id"], with_checkpoints=False)
                            for h in hits) if s]

    def resume_pack(self, task_id: str, *, max_checkpoints: int = 3,
                    max_chars: int = 1800) -> str:
        """生成注入 LLM 的恢复上下文包：目标 + 计划进度 + 最近检查点。"""
        snap = self.get_task(task_id)
        if snap is None:
            return f"（任务 {task_id} 不存在）"
        lines = [f"# 长任务恢复包 [{snap.task_id}]",
                 f"目标：{snap.objective}",
                 f"状态：{snap.status}"]
        if snap.plan:
            done = sum(1 for s in snap.plan if s.get("done"))
            lines.append(f"计划（{done}/{len(snap.plan)} 完成）：")
            for i, s in enumerate(snap.plan):
                lines.append(f"  [{'x' if s.get('done') else ' '}] {i}. {s.get('step','')}")
        recent = snap.checkpoints[-max_checkpoints:]
        if recent:
            lines.append("最近检查点：")
            for c in recent:
                note = (c["note"] or "").strip().replace("\n", " ")
                lines.append(f"  #{c['seq']} {note[:200]}")
                if c.get("artifacts"):
                    lines.append(f"      产物：{json.dumps(c['artifacts'], ensure_ascii=False)[:200]}")
        if snap.open_steps:
            lines.append("下一步建议：" + "；".join(snap.open_steps[:3]))
        pack = "\n".join(lines)
        return pack[:max_chars] + ("…（截断）" if len(pack) > max_chars else "")

    # ---------------- 内部 ----------------

    def _row(self, task_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM longtasks WHERE task_id=?", (task_id,)).fetchone()

    def _require(self, task_id: str) -> sqlite3.Row:
        row = self._row(task_id)
        if row is None:
            raise KeyError(f"任务不存在: {task_id}")
        return row

    def close(self) -> None:
        self.conn.close()
