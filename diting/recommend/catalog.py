# -*- coding: utf-8 -*-
"""商品/内容目录：JSON 装载 + 合成种子目录。

真实接入时把平台商品数据导出为同 schema 的 JSON 即可（或用 load_catalog(path=...)
指向自己的目录文件）。种子目录全部为**合成示例**（synthetic: true），
品牌名虚构，用于演示与回测，不构成对任何真实商品的评价。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SEED_CATALOG = Path(__file__).resolve().parent / "seed_catalog.json"


@dataclass
class Item:
    item_id: str
    title: str
    category: str                      # 品类（中文显示用）
    interest_key: str = ""             # 对应画像 interest_* 键（watcher 联动）
    merchant: str = ""                 # 商家名（恶意商家核查用）
    description: str = ""
    price: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    reviews: List[Dict[str, Any]] = field(default_factory=list)  # [{text, author, created_at}]
    synthetic: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def index_text(self) -> str:
        return f"{self.title}\n{self.description}\n{' '.join(self.tags)}"

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        return d


def load_catalog(path: Optional[str] = None) -> List[Item]:
    """从 JSON 装载目录；缺省用内置合成种子目录。"""
    p = Path(path) if path else SEED_CATALOG
    raw = json.loads(p.read_text(encoding="utf-8"))
    items: List[Item] = []
    for row in raw.get("items", []):
        known = {k: v for k, v in row.items() if k in Item.__dataclass_fields__}
        extra = {k: v for k, v in row.items() if k not in Item.__dataclass_fields__}
        it = Item(**known)
        it.meta.update(extra)
        items.append(it)
    return items
