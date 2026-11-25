# -*- coding: utf-8 -*-
"""长任务记忆（long-task memory）。

在 Hermes 会话记忆之上叠加**结构化任务层**：跨会话的任务登记、检查点、
中断恢复。典型场景：

  「帮我持续盯着清澜这个品牌的舆情」 —— 任务存活数周，每次会话推进一点，
  代理重启/换设备后凭 resume_pack 无损续接。

设计（docs 决策 D-05 延伸）：
- 任务 = longtasks 表一行（objective/plan/status/session_ids）
- 推进 = 追加检查点行（append-only，note + 任意 state JSON + artifacts）
- 恢复 = resume_pack() 生成给 LLM 的上下文包（目标 + 最新检查点 + 未完成事项）
- 与 geo_guard 三层记忆的关系：情景记忆存「甄别过什么」，本模块存「任务进行到哪」，
  互不替代；画像永不写入任务状态（判定公正性红线同样适用于任务排序）。
"""

from .store import LongTaskMemory, TaskSnapshot

__all__ = ["LongTaskMemory", "TaskSnapshot"]
