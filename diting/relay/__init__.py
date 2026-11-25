# -*- coding: utf-8 -*-
"""中转站（OpenAI 兼容 relay）诊断与修复。

背景：部分国内中转站（如 micuapi.ai，new-api 系）裸域名会 301 重定向到 www 子域。
HTTP 客户端（httpx/urllib）在跨域重定向时会剥离 Authorization 头、并把 POST 降级为
GET，导致「配了密钥却 401 Invalid token」或「模型列表为空」。

本模块提供：
- resolve_base_url()  带记忆化的重定向解析（探测一次，进程内缓存）
- diagnose()          全面体检：DNS / TLS / 重定向 / models 端点 / relay 指纹 / v1 后缀
- fix_config()        扫描 hermes config.yaml，把会重定向的 base_url 重写为最终 URL

红线：只探测 URL 结构，不上传密钥内容；--api-key 仅用于本机发起的鉴权探测。
"""

from .normalize import resolve_base_url, resolve_chain
from .doctor import RelayDiagnosis, diagnose

__all__ = ["resolve_base_url", "resolve_chain", "RelayDiagnosis", "diagnose"]
