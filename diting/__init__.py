# -*- coding: utf-8 -*-
"""谛听 Diting —— 个人平台治理智能体创新层。

在 Hermes Agent（MIT, Nous Research）之上叠加：
- geo_guard   GEO 逆向甄别内核（五库 RAG / 混合检索 / 三层判定融合）
- longtask    长任务记忆（跨会话任务登记 + 检查点 + 恢复）
- watcher     授权制浏览画像（默认关闭，本地聚合，可一键清除）
- recommend   避毒推荐引擎（内容相似 + 协同信号 + GEO 安全门）
- relay       中转站诊断与修复（OpenAI 兼容 relay 兼容性）
- backtest    回测框架（合成对抗语料 + 指标报告）

红线（全模块遵守）：
- 用户画像永不影响风险判定分数，只调制呈现（判定公正性 D-08）
- 知识库只做防御视角抽象，不含可操作投毒方法
- 浏览数据采集必须显式授权，密钥仅从环境变量读取
"""

__version__ = "0.1.0"

PRODUCT_NAME = "谛听 Diting"
PRODUCT_TAGLINE = "听万物 · 辨真伪"
