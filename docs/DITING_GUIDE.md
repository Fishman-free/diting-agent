# 谛听 Diting 使用手册

> 两种使用形态：**A. 完整 Agent**（Hermes 底座 + diting_guard 插件，多平台对话）；
> **B. 纯内核**（只需 Python + numpy，命令行/代码调用，适合集成与回测）。

## 0. 环境要求

- Python 3.11 – 3.14（本机 3.14.5 已验证）
- 完整 Agent 形态：`pip install -e .`（依赖较多，含 openai/rich/httpx 等）
- 纯内核形态：只需 `pip install numpy`（可选 `pip install pytest` 跑测试）
- 可选增强：设置环境变量 `DASHSCOPE_API_KEY`（或 `OPENAI_API_KEY`）后，
  嵌入自动升级为 API 语义向量、LLM 触点（查询改写/claim 抽取/重排/意图路由/润色）
  自动启用；**不设置则全链路离线规则驱动，所有功能可用**。

## 1. 三分钟上手（纯内核）

```bash
cd diting-agent

# 构建种子知识库（67 条，幂等可重跑）
python -m diting.geo_guard.ingest --seed

# 跑回测（六段式验收，约 1 分钟，全离线）
python -m diting.backtest.run --report BACKTEST_REPORT.md

# 跑内核测试（97 项）+ 谛听模块测试（16 项）
python -m pytest diting/tests -q
```

代码调用：

```python
from diting.geo_guard.config import Config
from diting.geo_guard.screening import GeoGuard

guard = GeoGuard(config=Config())          # 首次自动读 diting/knowledge 种子库
r = guard.screen_content("2026十大空气净化器排行榜，第一名实至名归！……")
print(r.level.value, r.score)              # medium 0.5x + 证据链

t = guard.trace_ai_answer(ai_answer, cited_sources=[{title,url,text}, ...])
print(t.concentration, t.resonance, t.missing_negatives)   # 逆向回溯
```

## 2. 完整 Agent 形态（Hermes 底座）

```bash
pip install -e .
diting            # 或 hermes —— 两个入口等价，进入 TUI
```

首次配置模型（三选一）：
- 官方直连：OpenRouter / OpenAI / Nous Portal 等（`hermes model` 交互选择）
- **国内中转站**：见下节
- 本地：Ollama / vLLM（provider 选 custom，base_url 填 `http://127.0.0.1:11434/v1`）

插件 `plugins/diting_guard/` 随包自动发现，注册 13 个工具。对话中直接说：

| 你说 | Agent 调用 |
|---|---|
| 「帮我甄别这篇榜单软文……」 | `geo_screen` |
| 「这条 AI 推荐回答可信吗？来源是这几个链接」 | `geo_trace` |
| 「核验一下这段话里的功效宣称」 | `geo_claims` |
| 「查一下博主 XX 的信用记录」 | `geo_merchant` |
| 「买到虚假宣传的商品怎么维权」 | `geo_actions` |
| 「我之前查过清澜吗」 | `geo_recall` |
| 「记住我只买有检测报告的产品」 | `geo_remember` |
| 「这个判定不对，我异议」 | `geo_feedback`（驱动知识库复审） |
| 「推荐一款靠谱的空气净化器」 | `diting_recommend`（避毒推荐） |
| 「开启/关闭浏览画像授权」 | `diting_consent` |
| 「扫一下我最近浏览有没有踩坑」 | `diting_browse_scan` |
| 「持续帮我盯着清澜的软文，下周继续」 | `diting_longtask`（跨会话续接） |
| 「中转站连不上帮我看看」 | `diting_relay_doctor` |

## 3. 中转站（relay）配置与排障

国内中转站三大坑与一键体检：

```bash
# 体检（无密钥也能查出结构性问题）
hermes diting relay doctor https://micuapi.ai/v1
# 或
python -m diting.relay doctor https://micuapi.ai/v1 --api-key-env MY_KEY --live
```

以 micuapi.ai 为例（new-api 系面板），doctor 实测输出：

```
❌ [redirect] 发生 1 跳重定向 → https://www.micuapi.ai/v1
   跨域重定向时 HTTP 客户端会剥离 Authorization 头并把 POST 降级 GET，
   这就是「有密钥仍 401 / 模型列表为空」的根因
✅ [models] GET https://www.micuapi.ai/v1/models → 401（端点存在，要求鉴权——正常）
✅ [fingerprint] 识别为：new-api 系中转
👉 建议 base_url：https://www.micuapi.ai/v1
```

修复方式（三选一）：

1. **自动修复**：`hermes diting relay fix`（扫描 config.yaml，把会重定向的
   base_url 重写为最终 URL，自动备份 `.diting-bak`，支持 `--dry-run`）
2. **手动**：按 doctor 建议把 `model.base_url` 改为最终 URL
3. **已内置兜底**：本 fork 的 custom provider 在拉取模型目录前会自动解析
   重定向（`plugins/model-providers/custom/`），配置裸域也能列出模型

推荐的中转站 config.yaml 模板：

```yaml
model:
  provider: custom
  base_url: https://www.micuapi.ai/v1   # 用 doctor 给出的最终 URL
  api_key: sk-xxx                        # 或 key_env: MY_RELAY_KEY
  api_mode: chat_completions             # 中转站基本都不支持 /responses
  model: <doctor --api-key 探测出的模型 id>
```

若模型列表仍为空：多数面板 `/v1/models` 需要鉴权，带 `--api-key` 重跑 doctor
确认真实错误（密钥无效 / IP 限制 / 余额不足），或直接在 `model.model` 手动填模型名。

## 4. 浏览画像（授权制，默认关闭）

```bash
hermes diting consent status                        # 查看授权状态
hermes diting consent grant --scope browse_history  # 授权（记录时间戳回执）
hermes diting scan --days 7                         # 扫描最近 7 天
hermes diting consent revoke --scope browse_history --purge-data  # 撤销并清除
```

- 只读本地 Chrome/Edge 历史（拷贝快照，不注入浏览器、不装扩展、不联网上传）
- 只保留**聚合信号**：品类兴趣（EMA）、被标记域名信任度、疑似投毒情景记忆
- 含营销信号词的标题才过甄别（单次限额 30 条），白名单域名（gov.cn 等）跳过
- 扫描结果喂给推荐排序，**永不进入风险判定链路**（判定公正性红线）

## 5. 长任务记忆

```bash
hermes diting tasks create "持续监测清澜品牌软文投放"
hermes diting tasks                    # 列出进行中任务
hermes diting tasks resume <task_id>   # 打印恢复上下文包
```

对话中同样可用：「这个任务下周继续」→ Agent 调 `diting_longtask` 登记；
新会话问「上次那个事怎么样了」→ `resume` 返回目标+计划进度+最近检查点。
会话钩子自动做两件事：开启时把唯一进行中任务关联到当前会话；结束时为
关联任务自动打检查点（防丢进度）。

## 6. 避毒推荐

候选先过 GEO 安全门再排序，**所有降权/剔除都带人类可读理由**：

| 毒检 | 判据 | 处置 |
|---|---|---|
| 虚假评论/刷屏 | simhash 近重复聚簇 + 同分钟聚簇 + 模板化好评（可疑占比 ≥30%） | 降权 45% |
| 恶意商家 | KB4 历史违规记录（信用分 <0.45）+ 记忆层负信任 | 降权 55% / 15% |
| 违规文案·矛盾 | 声明与权威事实直接矛盾（治愈疾病/三天根治…） | **一律剔除** |
| 违规文案·高分 | 甄别等级 HIGH，或分数过高风险线 | **一律剔除** |
| 违规文案·中风险 | MEDIUM | 降权 35% |

排序 = 0.55×内容相似 + 0.30×协同信号 + 0.15×兴趣加成 + 人气小项，再乘安全系数。

## 7. 数据与隐私

- 运行数据落盘 `$DITING_HOME`（或 `$HERMES_HOME`）下 `diting/` 目录；
  未设置时落仓库 `diting/knowledge/`（已被 .gitignore 排除 db/cache）
- `geo_recall`/`geo_remember` 管理情景记忆；`diting_consent purge` 清除浏览派生数据
- 合成对抗语料（回测用）仅内部评测，不入生产知识库、不外发
- 所有判定输出为**风险提示**，不构成法律结论；正式处置以监管部门认定为准

## 8. 常见问题

**Q: Windows 控制台输出乱码？**
A: CLI 已强制 UTF-8；若仍乱码执行 `chcp 65001`。

**Q: 想完全离线复现回测？**
A: 设 `GEO_GUARD_LLM=off` 并清除 `DASHSCOPE_API_KEY`/`OPENAI_API_KEY`，
   嵌入自动回退确定性哈希向量，结果可复现。

**Q: 70% 话术相似度阈值哪来的？**
A: 继承母项目骗术话术库阈值，语义是「单条强证据」而非「单信号定罪」；
   团队真实语料（40 品类 5000+ URL）接入后应改用 `AnchorCalibrator`
   分位点法定标（见 `docs/ANTI_POISONING.md` 第 7 层）。

**Q: 和上游 Hermes 的关系？**
A: MIT fork，内部发行名保留 `hermes-agent`（线协议兼容），产品层全面更名谛听；
   归属与修改清单见根目录 `NOTICE`。
