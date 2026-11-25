# -*- coding: utf-8 -*-
"""插件级懒加载单例：首次工具调用时才初始化内核（注册阶段零开销）。

数据落盘位置：$DITING_HOME/diting/ > $HERMES_HOME/diting/ > 仓库 diting/knowledge/。
运行数据跟随用户 home，不污染仓库工作树。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: Optional["DitingState"] = None


def _data_dir() -> Path:
    home = os.environ.get("DITING_HOME") or os.environ.get("HERMES_HOME") or ""
    if home:
        d = Path(home).expanduser() / "diting"
    else:
        d = Path(__file__).resolve().parent.parent.parent / "diting" / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


class DitingState:
    """内核各组件的持有者（一个进程一份）。"""

    def __init__(self, user_id: str = "default"):
        from diting.geo_guard.config import Config
        from diting.geo_guard.ingest import IngestPipeline
        from diting.geo_guard.kb.store import KnowledgeStore
        from diting.geo_guard.memory import MemoryStore
        from diting.geo_guard.plugin import GeoGuardPlugin
        from diting.geo_guard.screening import GeoGuard
        from diting.longtask import LongTaskMemory
        from diting.recommend import SafeRecommender
        from diting.watcher import ConsentManager, WatcherState

        d = _data_dir()
        self.config = Config(db_path=str(d / "geoguard.db"), cache_dir=str(d / "cache"))
        self.store = KnowledgeStore(self.config)
        # 幂等种子构建：首次使用自动就绪，无需手动 seed
        self.seed_counts = IngestPipeline(self.store, self.config).seed_from_dir()
        self.guard = GeoGuard(store=self.store, config=self.config)
        self.memory = MemoryStore(self.config, db_path=str(d / "memory.db"), user_id=user_id)
        self.core = GeoGuardPlugin(user_id=user_id, guard=self.guard,
                                   memory=self.memory, config=self.config)
        self.consent = ConsentManager(db_path=str(d / "diting.db"), user_id=user_id)
        self.watcher_state = WatcherState(db_path=str(d / "diting.db"), user_id=user_id)
        self.longtask = LongTaskMemory(db_path=str(d / "longtask.db"), user_id=user_id)
        self.recommender = SafeRecommender(self.guard, self.memory,
                                           db_path=str(d / "recommend.db"), user_id=user_id)
        logger.info("DitingState ready: kb=%d active, data_dir=%s",
                    self.store.count(), d)

    def close(self) -> None:
        for attr in ("recommender", "longtask", "watcher_state", "consent",
                     "memory", "store"):
            try:
                getattr(self, attr).close()
            except Exception:
                pass


def get_state(user_id: str = "default") -> DitingState:
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                _state = DitingState(user_id=user_id)
    return _state
