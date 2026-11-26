# 谛听 Diting 使用手册

> 三种使用形态：**A. 完整 Agent CLI**（Hermes 底座 + diting_guard 插件，多平台对话）；
> **B. 桌面版**（Electron 原生窗口，图形界面管理会话/记忆/画像）；
> **C. 纯内核**（只需 Python + numpy，命令行/代码调用，适合集成与回测）。

## 0. 环境要求

- Python 3.11 – 3.14（本机 3.14.5 已验证）
- 完整 Agent 形态：`pip install -e .`（依赖较多，含 openai/rich/httpx 等）
- 纯内核形态：只需 `pip install numpy`（可选 `pip install pytest` 跑测试）
- 桌面版：仓库根 `pnpm install`（pm 工具链会自动引导 node/pnpm，见 §2）
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

# 跑内核测试 + 谛听模块测试（121 项）
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

### CLI 一键启动（推荐）

双击桌面 **「谛听 Diting」图标** 即进入对话界面（经典 CLI；TUI 需 `hermes --tui`
或配置 `display.interface: tui`）。图标不存在时生成一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_desktop_shortcut.ps1
```

首次双击自动完成：创建仓库内隔离 `.venv` → 用 uv 安装依赖（上游
`[tool.uv] override-dependencies` 会应用 Pillow 安全修复版 override，
裸 pip 在 Python 3.14 下解析不了该冲突）→ 构建种子知识库。此后双击直达。
图标指向 `scripts/launch_diting.bat`；换机器/换目录后重跑上面那条命令即可。

### 桌面版（Electron 原生窗口）

双击桌面 **「谛听 Diting 桌面版」图标**，或：

```bash
hermes desktop --source        # 源码模式：构建前端资产后以 electron 启动（推荐）
scripts\launch_diting_desktop.bat   # 等价的一键脚本（自动补 .venv）
```

- 首次启动会自动引导托管 node/pnpm 工具链并构建前端资产（数分钟），之后启动很快
- 桌面端自动以本仓库为后端内核（spawn `hermes gateway ensure`），无需另行起服务
- 图形界面覆盖：对话/流式输出、会话管理、技能、定时任务、模型服务商配置、
  **设置 → 记忆与上下文 → 「谛听画像与长程记忆」面板**（查看/编辑 USER.md 与
  MEMORY.md 条目、兴趣信号、授权状态、进行中长任务，并附等效命令提示）
- 图标指向 `scripts/launch_diting_desktop.bat`，生成方式：
  `powershell -ExecutionPolicy Bypass -File scripts\make_desktop_shortcut.ps1`

### 命令行启动

```bash
pip install -e .
diting            # 或 hermes —— 两个入口等价
```

首次配置模型（三选一）：
- 官方直连：OpenRouter / OpenAI / Nous Portal 等（`hermes model` 交互选择）
- **国内中转站**：见下节
- 本地：Ollama / vLLM（provider 选 custom，base_url 填 `http://127.0.0.1:11434/v1`）

插件 `plugins/diting_guard/` 随包分发，默认未启用。**终端命令 `hermes diting …`
开箱即用**（主 CLI 内置挂载，不依赖 `plugins.enabled`）；对话内工具需一次性启用，
启用后注册 13 个工具：

```bash
hermes plugins enable diting-guard
```

对话中直接说：

| 你说 | Agent 调用 |
|---|---|
| 「帮我甄别这篇榜单软文……」 | `geo_screen` |
| 「这条 AI 推荐回答可信吗？来源是这几个链接」 | `geo_trace` |
| 「核验一下这段话里的功效宣称」 | `geo_claims` |
| 「查一下博主 XX 的信用记录」 | `geo_merchant` |
| 「买到虚假宣传的商品怎么维权」 | `geo_actions` |
| 「我之前查过清澜吗」 | `geo_recall` |
| 「记住我只买有检测报告的产品」 | `geo_remember`（写入 USER.md 画像） |
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

## 6. 用户画像与长程记忆（查看 / 修改）

谛听把「你是谁」（**用户画像 USER.md**）和「代理记住了什么」（**长程记忆
MEMORY.md**）做成一等公民：三个入口读写**同一份数据**，永远一致——
CLI 命令、桌面版面板（设置 → 记忆与上下文）、对话中直接吩咐 Agent。

```bash
# ── 用户画像（USER.md：身份、偏好、长期约定；聚合视图另含兴趣信号/授权/长任务）──
hermes diting profile                          # 查看全部画像（含谛听扩展画像）
hermes diting profile add 偏好简体中文回复      # 新增一条
hermes diting profile remove 偏好简体中文       # 按关键词删除整条
hermes diting profile replace 偏好简体中文 偏好中文、术语保留英文   # 整条替换
hermes diting profile patch 偏好中文 偏好简体中文                   # 局部改写

# ── 长程记忆（MEMORY.md：代理的持久笔记与事实）──
hermes diting memory                           # 查看全部记忆与用量
hermes diting memory add 项目仓库在 Desktop/diting-agent
hermes diting memory remove 项目仓库
hermes diting memory replace 项目仓库 仓库已迁至新路径 X
hermes diting memory patch 旧路径 新路径
```

- 全部命令带完整提示：`hermes diting help` 输出命令全览；任意子命令加 `-h`
  看参数与示例；`status` 尾部也有指路
- 修改即时落盘（文件锁保护，多进程安全），下次会话自动进入系统提示词
- 有字符限额（MEMORY.md 2200 / USER.md 1375），超限时命令会给出当前条目
  让你先清理——这是内核 `memory` 工具的同一套规则
- 关键词定位有歧义时会列出候选条目，换更精确的子串即可
- 对话中等效：「看下我的用户画像」「记住我只买有检测报告的产品」——
  Agent 通过内置 `memory` 工具读写同一对文件
- 桌面版等效：设置 → 记忆与上下文 → 「谛听画像与长程记忆」面板，
  可视化增删改，底部附全部等效命令
- `hermes diting …` 由主 CLI 内置挂载，**无需启用插件、无需先配置模型**；
  干净环境下直接可用（数据落 `$HERMES_HOME/memories/`）

## 7. 避毒推荐

候选先过 GEO 安全门再排序，**所有降权/剔除都带人类可读理由**：

| 毒检 | 判据 | 处置 |
|---|---|---|
| 虚假评论/刷屏 | simhash 近重复聚簇 + 同分钟聚簇 + 模板化好评（可疑占比 ≥30%） | 降权 45% |
| 恶意商家 | KB4 历史违规记录（信用分 <0.45）+ 记忆层负信任 | 降权 55% / 15% |
| 违规文案·矛盾 | 声明与权威事实直接矛盾（治愈疾病/三天根治…） | **一律剔除** |
| 违规文案·高分 | 甄别等级 HIGH，或分数过高风险线 | **一律剔除** |
| 违规文案·中风险 | MEDIUM | 降权 35% |

排序 = 0.55×内容相似 + 0.30×协同信号 + 0.15×兴趣加成 + 人气小项，再乘安全系数。

## 8. 技能自进化（self-evolution）

集成自 [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)
（MIT，vendor 于 `evolution/`，溯源与本地补丁见 `evolution/VENDOR.md`）：
用 DSPy + GEPA 反思式进化优化技能文件（SKILL.md），纯 API 调用、无需 GPU。

```bash
# 安装可选依赖（dspy + click；模型 key 仅走环境变量，零硬编码）
uv pip install -e ".[evolution]"
export OPENAI_API_KEY=...        # 或 OPENROUTER_API_KEY 等 LiteLLM 支持的任意提供商

# 验证环境与技能定位（不花 token）
hermes diting evolve github-code-review --dry-run

# 合成评测集进化（约 $2-10/次）
hermes diting evolve arxiv --iterations 10

# 挖掘本机会话历史（Claude Code / Copilot / Hermes）做评测集
hermes diting evolve arxiv --eval-source sessiondb
```

- 约束门原样生效：pytest 全绿、技能 ≤15KB、语义不漂移、禁止会话中途变更
- 产物落 `evolution/output/<技能>/<时间戳>/`（evolved_skill.md + baseline + metrics），
  **仅供人工评审，绝不自动落库**；确认后手动替换 skills/ 下对应 SKILL.md
- 上游原生命令同样可用：`python -m evolution.skills.evolve_skill --skill <名>`

## 9. 数据与隐私

- 运行数据落盘 `$DITING_HOME`（或 `$HERMES_HOME`）下 `diting/` 目录；
  未设置时落仓库 `diting/knowledge/`（已被 .gitignore 排除 db/cache）
- 画像与长程记忆落 `$HERMES_HOME/memories/`（USER.md / MEMORY.md）
- `geo_recall`/`geo_remember` 管理情景记忆；`diting_consent purge` 清除浏览派生数据
- 合成对抗语料（回测用）仅内部评测，不入生产知识库、不外发
- 所有判定输出为**风险提示**，不构成法律结论；正式处置以监管部门认定为准

## 10. 常见问题

**Q: Windows 控制台输出乱码？**
A: CLI 已强制 UTF-8；若仍乱码执行 `chcp 65001`。

**Q: 想完全离线复现回测？**
A: 设 `GEO_GUARD_LLM=off` 并清除 `DASHSCOPE_API_KEY`/`OPENAI_API_KEY`，
   嵌入自动回退确定性哈希向量，结果可复现。

**Q: 70% 话术相似度阈值哪来的？**
A: 继承母项目骗术话术库阈值，语义是「单条强证据」而非「单信号定罪」；
   团队真实语料（40 品类 5000+ URL）接入后应改用 `AnchorCalibrator`
   分位点法定标（见 `docs/ANTI_POISONING.md` 第 7 层）。

**Q: 桌面版启动报 Node 依赖错误？**
A: 桌面版走仓库根 pnpm workspace：先在仓库根执行 `pnpm install`（pm 会自动
   引导合规 node/pnpm），Electron 二进制用
   `node scripts/build/electron-runtime.mjs --source .` 准备（国内网络可加
   `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`）。

**Q: 和上游 Hermes 的关系？**
A: MIT fork，内部发行名保留 `hermes-agent`（线协议兼容），产品层全面更名谛听；
   `evolution/` vendor 自 NousResearch/hermes-agent-self-evolution（MIT）。
   归属与修改清单见根目录 `NOTICE`。
