# -*- coding: utf-8 -*-
"""避毒推荐引擎（GEO-safe recommendation）。

算法模式借鉴（均在 numpy 上轻量实现，不引入重型依赖）：
- 内容相似：TF-IDF + 余弦（scikit-learn 教程的标准内容推荐模式；
  分词复用 geo_guard 的中文 bigram tokenizer，DRY）
- 协同信号：item-item 共现（implicit/RecBole 的隐式反馈 item-item CF 模式，
  共现计数余弦代替 ALS——单机数据量级下等价且免编译依赖）
- 混合排序：relevance = 0.6×内容相似 + 0.4×协同信号 + 品类兴趣加成

**项目特色（区别于所有开源推荐库）——GEO 安全门**：
候选在进入排序前先过四道毒检：
  ① 虚假评论/刷屏水军（CommentAnalyzer：近重复聚簇 + 同分钟聚簇 + 模板化好评）
  ② 恶意商家（KB4 历史记录 + 记忆层实体信任度）
  ③ 违规宣传话术（screen_content：绝对化用语/疗效宣称/榜单操纵句式）
  ④ 高风险直接剔除并说明理由，中风险降权——**降权永远带人类可读理由**，
     不做静默过滤（用户有权知道「为什么没给我看这个」）

红线：推荐排序可以使用画像（这正是推荐的目的），但画像永不回流
screen_content 的风险判定分数（D-08 判定公正性）。
"""

from .catalog import Item, load_catalog
from .engine import SafeRecommender, RecommendEntry, RecommendResult, SafetyVerdict, render_result

__all__ = ["Item", "load_catalog", "SafeRecommender", "RecommendEntry",
           "RecommendResult", "SafetyVerdict", "render_result"]
