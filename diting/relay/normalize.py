# -*- coding: utf-8 -*-
"""base_url 重定向解析（记忆化，离线安全）。

探测策略：无鉴权 GET（HEAD 部分 relay 不支持，统一用 GET），手动跟随重定向并记录
跳转链；任何网络/证书错误 → 返回原值（绝不因探测失败阻断主流程）。
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_UA = "diting-relay-doctor/1.0 (+https://github.com/Fishman-free/diting-agent)"
_MAX_HOPS = 5

_cache: Dict[str, "ResolveResult"] = {}
_lock = threading.Lock()


class _RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """记录每一跳的重定向处理器（不自动跟随，由 resolve_chain 手动驱动）。"""

    def __init__(self) -> None:
        self.chain: List[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.chain.append(newurl)
        if len(self.chain) >= _MAX_HOPS:
            return None  # 防重定向环：停止跟随
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class ResolveResult:
    """一次解析的完整结果。"""

    original: str
    final_url: str
    hops: List[str] = field(default_factory=list)   # 每一跳的目标（含最终）
    status: int = 0                                  # 最终响应码（0 = 探测失败）
    error: str = ""                                  # 失败原因（DNS/TLS/超时…）
    redirected: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


def resolve_chain(url: str, *, timeout: float = 6.0, method: str = "GET") -> ResolveResult:
    """跟随重定向解析 *url*，返回最终 URL 与跳转链。失败返回原 URL（error 非空）。"""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return ResolveResult(original=url, final_url=url, error="not an http(s) url")
    handler = _RecordingRedirectHandler()
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", _UA)
    req.add_header("Accept", "application/json, text/plain, */*")
    try:
        with opener.open(req, timeout=timeout) as resp:
            body_status = resp.status
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        # 4xx/5xx 也是有效探测结果：URL 可达，只是端点/鉴权问题
        final = exc.url or (handler.chain[-1] if handler.chain else url)
        body_status = exc.code
    except Exception as exc:  # URLError(DNS/TLS/超时) 等
        reason = str(getattr(exc, "reason", exc))[:200]
        return ResolveResult(original=url, final_url=url, hops=list(handler.chain),
                             error=reason)
    redirected = bool(handler.chain)
    return ResolveResult(original=url, final_url=final, hops=list(handler.chain),
                         status=body_status, redirected=redirected)


def resolve_base_url(url: str, *, timeout: float = 5.0) -> str:
    """记忆化解析：返回重定向后的最终 base_url；任何失败返回原值。

    供 custom provider 探测与插件启动检查调用——每个 URL 每进程只探测一次。
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return url
    with _lock:
        cached = _cache.get(url)
    if cached is not None:
        return cached.final_url if cached.ok else url
    result = resolve_chain(url, timeout=timeout)
    with _lock:
        _cache[url] = result
    return result.final_url if result.ok else url


def cached_resolve(url: str) -> Optional[ResolveResult]:
    """读取已有缓存（无缓存返回 None，不发起网络）——供告警 hook 零成本查询。"""
    with _lock:
        return _cache.get((url or "").strip().rstrip("/"))


def prime(url: str, *, timeout: float = 5.0) -> ResolveResult:
    """主动探测并写入缓存，返回完整结果（诊断/启动检查用）。"""
    url = (url or "").strip().rstrip("/")
    result = resolve_chain(url, timeout=timeout)
    with _lock:
        _cache[url] = result
    return result
