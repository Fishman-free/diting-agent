# -*- coding: utf-8 -*-
"""relay doctor：OpenAI 兼容中转站一键体检。

体检项（按序短路友好，但全部执行以给完整报告）：
  dns        域名解析
  tls        HTTPS 证书握手
  redirect   301/302 重定向链（跨域重定向 = 鉴权头丢失高危）
  v1         是否缺 /v1 后缀（404 → 探测补全）
  models     GET {base}/models 无鉴权可达性与响应形态
  auth       （提供密钥时）Bearer 鉴权探测 → 模型数与样例
  chat       （--live 时）最小 chat/completions 请求实测
  fingerprint relay 软件指纹（new-api / one-api / cloudflare WAF …）

用法：
  python -m diting.relay doctor https://micuapi.ai/v1 [--api-key sk-xx] [--live] [--json]
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .normalize import ResolveResult, resolve_chain

_UA = "diting-relay-doctor/1.0 (+https://github.com/Fishman-free/diting-agent)"

# relay 软件/防护的响应指纹（错误体或响应头特征 → 人类可读结论）
_FINGERPRINTS = [
    ("new_api_error", "new-api 系中转（国内主流 relay 面板），支持 OpenAI /v1 协议"),
    ("one-api", "one-api 系中转，支持 OpenAI /v1 协议"),
    ("voapi", "voapi 系中转"),
    ("cloudflare", "Cloudflare 防护/WAF —— 若返回 403 HTML，需浏览器质询或换 UA"),
    ("Invalid token", "relay 判定密钥无效（也可能是重定向剥掉了 Authorization 头）"),
    ("令牌", "relay 中文错误提示（new-api/one-api 面板常见）"),
]


@dataclass
class Check:
    name: str
    status: str            # ok | warn | fail | skip
    detail: str = ""


@dataclass
class RelayDiagnosis:
    url: str
    final_url: str = ""
    checks: List[Check] = field(default_factory=list)
    suggested_base_url: str = ""
    model_count: int = 0
    sample_models: List[str] = field(default_factory=list)
    fingerprint: str = ""
    suggested_config: str = ""   # 可直接粘贴的 config.yaml 片段

    @property
    def healthy(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "final_url": self.final_url,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                       for c in self.checks],
            "suggested_base_url": self.suggested_base_url,
            "model_count": self.model_count, "sample_models": self.sample_models,
            "fingerprint": self.fingerprint, "healthy": self.healthy,
        }


def _http_get(url: str, *, api_key: str = "", timeout: float = 8.0) -> tuple:
    """GET → (status, body_text, headers)。不跟随重定向（体检要看原始行为）。"""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):  # noqa: N802
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _UA)
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(65536).decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(65536).decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, body, dict(exc.headers or {})
    except Exception as exc:
        return 0, str(getattr(exc, "reason", exc))[:300], {}


def _parse_models(body: str) -> tuple:
    """解析 /models 响应 → (count, samples)。支持 OpenAI {data:[...]} 与裸列表。"""
    try:
        data = json.loads(body)
    except Exception:
        return 0, []
    items = data if isinstance(data, list) else (data.get("data") or [])
    ids: List[str] = []
    for it in items:
        if isinstance(it, str):
            ids.append(it)
        elif isinstance(it, dict) and it.get("id"):
            ids.append(str(it["id"]))
    return len(ids), ids[:8]


def diagnose(url: str, *, api_key: str = "", live: bool = False,
             timeout: float = 8.0) -> RelayDiagnosis:
    """对 *url*（relay 的 base_url，可含或不含 /v1）做全面体检。"""
    url = (url or "").strip().rstrip("/")
    diag = RelayDiagnosis(url=url)
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname or ""

    # 1) DNS
    try:
        socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        diag.checks.append(Check("dns", "ok", f"{host} 解析成功"))
    except Exception as exc:
        diag.checks.append(Check("dns", "fail",
                                 f"{host} 解析失败：{exc}。常见原因：中转站没有 api. 子域，"
                                 f"请用官网给出的真实端点（跑 doctor 前确认域名拼写）"))
        diag.suggested_base_url = url
        return diag

    # 2) 重定向 + TLS（resolve_chain 一并覆盖：证书错误会进 error）
    res: ResolveResult = resolve_chain(url, timeout=timeout)
    if res.error and "CERTIFICATE" in res.error.upper():
        diag.checks.append(Check("tls", "fail", f"证书校验失败：{res.error}"))
    elif res.error:
        diag.checks.append(Check("tls", "warn", f"连接失败：{res.error}"))
    else:
        diag.checks.append(Check("tls", "ok", "HTTPS 握手正常"))

    if res.redirected:
        diag.checks.append(Check(
            "redirect", "fail",
            f"发生 {len(res.hops)} 跳重定向 → {res.final_url}。跨域重定向时 HTTP 客户端会剥离 "
            f"Authorization 头并把 POST 降级 GET，这就是「有密钥仍 401 / 模型列表为空」的根因。"
            f"请把 base_url 改为重定向后的最终 URL"))
        diag.final_url = res.final_url
        base = res.final_url.rstrip("/")
    else:
        diag.checks.append(Check("redirect", "ok", "无重定向"))
        diag.final_url = url
        base = url

    # 3) /models 端点（无鉴权先看可达性，再带鉴权）
    probe_targets = [base, base + "/models"]
    status, body, _ = _http_get(base + "/models", timeout=timeout)
    v1_hint = ""
    if status in (404, 405) and not base.endswith("/v1"):
        # 缺 /v1 后缀的经典症状
        s2, b2, _ = _http_get(base + "/v1/models", timeout=timeout)
        if s2 not in (404, 405, 0):
            v1_hint = f"；但 {base}/v1/models 可达（{s2}）—— base_url 应以 /v1 结尾"
            base = base + "/v1"
            status, body = s2, b2
    if status == 0:
        diag.checks.append(Check("models", "fail", f"GET {base}/models 连接失败：{body[:160]}"))
    elif status in (401, 403):
        diag.checks.append(Check("models", "ok",
                                 f"GET {base}/models → {status}（端点存在，要求鉴权——正常）{v1_hint}"))
    elif status == 200:
        n, samples = _parse_models(body)
        diag.checks.append(Check("models", "ok",
                                 f"GET {base}/models → 200，公开目录 {n} 个模型{v1_hint}"))
        diag.model_count, diag.sample_models = n, samples
    else:
        diag.checks.append(Check("models", "warn",
                                 f"GET {base}/models → {status}（非标准响应）{v1_hint}"))

    # 4) 指纹识别（用无鉴权错误体 + 带鉴权错误体）
    fp_source = body
    if api_key:
        st_a, body_a, _ = _http_get(base + "/models", api_key=api_key, timeout=timeout)
        if st_a == 200:
            n, samples = _parse_models(body_a)
            diag.model_count, diag.sample_models = n, samples
            diag.checks.append(Check("auth", "ok", f"Bearer 鉴权通过，目录 {n} 个模型"))
        else:
            diag.checks.append(Check("auth", "fail",
                                     f"Bearer 鉴权失败（HTTP {st_a}）：{body_a[:200]}"))
            fp_source += "\n" + body_a
    else:
        diag.checks.append(Check("auth", "skip", "未提供 --api-key，跳过鉴权探测"))
    for needle, label in _FINGERPRINTS:
        if needle.lower() in fp_source.lower():
            diag.fingerprint = label
            break
    if diag.fingerprint:
        diag.checks.append(Check("fingerprint", "ok", f"识别为：{diag.fingerprint}"))

    # 5) --live：最小 chat 请求实测
    if live and api_key and diag.sample_models:
        model = diag.sample_models[0]
        payload = json.dumps({"model": model, "max_tokens": 1,
                              "messages": [{"role": "user", "content": "ping"}]}).encode()
        req = urllib.request.Request(base + "/chat/completions", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("User-Agent", _UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                diag.checks.append(Check("chat", "ok",
                                         f"POST chat/completions（model={model}）→ {resp.status} 实测通过"))
        except urllib.error.HTTPError as exc:
            eb = exc.read(2048).decode("utf-8", "replace")[:200]
            diag.checks.append(Check("chat", "fail", f"chat 实测 HTTP {exc.code}：{eb}"))
        except Exception as exc:
            diag.checks.append(Check("chat", "fail", f"chat 实测失败：{exc}"))
    elif live:
        diag.checks.append(Check("chat", "skip", "--live 需要 --api-key 且目录可枚举"))

    # 结论与修复建议
    diag.suggested_base_url = base
    diag.suggested_config = (
        "model:\n"
        "  provider: custom\n"
        f"  base_url: {base}\n"
        "  api_key: <你的密钥>          # 或 key_env: MY_RELAY_KEY\n"
        "  api_mode: chat_completions  # 中转站几乎都不支持 /responses，强制通用链路\n"
        "  model: <从上面目录里选一个模型 id>\n")
    return diag


def render(diag: RelayDiagnosis) -> str:
    icon = {"ok": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}
    lines = [f"🩺 relay doctor —— {diag.url}", ""]
    for c in diag.checks:
        lines.append(f"  {icon.get(c.status, '·')} [{c.name}] {c.detail}")
    lines.append("")
    if diag.suggested_base_url and diag.suggested_base_url != diag.url:
        lines.append(f"👉 建议 base_url：{diag.suggested_base_url}")
    if not diag.healthy:
        lines.append("👉 修复后配置片段（config.yaml）：")
        lines.append(diag.suggested_config)
    else:
        lines.append(f"👉 该端点结构健康。配置片段：\n{diag.suggested_config}")
    return "\n".join(lines)
