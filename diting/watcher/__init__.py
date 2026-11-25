# -*- coding: utf-8 -*-
"""授权制浏览画像守护（browse watcher）。

与平台连接、实时获得用户自我画像的**隐私优先**实现：
- 一切采集以显式授权为前提（consent 记录含时间戳，可审计、可撤销）
- 只读本地浏览器历史（Chrome/Edge，Windows/macOS/Linux），不注入浏览器、不装扩展
- 只保留聚合信号与被标记域名，不持久化完整浏览历史
- 甄别结果喂给 geo_guard 记忆层：实体信任度（域名）+ 画像兴趣键 + 情景记忆
- 一键清除：purge()

红线：画像数据永不回流风险判定分数（D-08）——watcher 输出只用于
「推荐排序」与「呈现调制」，screen_content 的判定链路对其不可见。
"""

from .consent import ConsentManager
from .state import WatcherState
from .browser_history import VisitRecord, read_browser_history, detect_browsers
from .profile_feed import process_visits, render_insight, BrowseInsight

__all__ = ["ConsentManager", "WatcherState", "VisitRecord", "read_browser_history",
           "detect_browsers", "process_visits", "render_insight", "BrowseInsight"]
