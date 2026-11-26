<div align="center">

# 谛听 Diting Agent

**听万物 · 辨真伪**

基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent)（MIT）深度定制的
**个人平台治理智能体** —— 以 GEO 逆向甄别为核心，带长任务记忆、授权制浏览画像与避毒推荐。

中国人民大学 2026 大学生创新训练计划「面向用户的平台治理支持智能体系统」· 产品与技术方案

[MIT License](LICENSE) · [归属声明](NOTICE) · [上游 README](docs/upstream-hermes-README.md)

</div>

---

## 为什么叫「谛听」

谛听是传说中能「坐地听八百，卧耳听三千」的神兽，**善听人心、能辨真伪**。
这正是本项目要做的事：在生成式引擎优化（GEO）投毒泛滥的信息环境里，
替用户**听**出软文、刷评、水军与注入攻击的弦外之音，**辨**出 AI 回答背后被污染的证据链。

> 背景：央视 3·15 晚会曝光 GEO「投毒」灰黑产——批量铺设软文/榜单/测评，
> 污染 AI 助手的联网检索证据供给（retrieval poisoning），让大模型「真诚地推荐假货」。

## 在 Hermes Agent 之上加了什么

| 能力 | 说明 | 代码位置 |
|---|---|---|
| 🛡️ **GEO 逆向甄别内核** | 五库 RAG + 混合检索 + 三层判定融合；单篇内容甄别 & AI 回答逆向回溯（来源集中度/话术共振度/反证缺失度） | `diting/geo_guard/` |
| 🔌 **diting_guard 插件** | 甄别/回溯/核验/维权/记忆/反馈 等工具注册进 Agent 工具系统，对话中直接调用 | `plugins/diting_guard/` |
| 🧠 **长任务记忆** | 跨会话任务登记 + 检查点 + 中断恢复，叠加在 Hermes 会话记忆之上 | `diting/longtask/` |
| 👁️ **授权制浏览画像** | 用户显式授权后读取本地浏览器历史，实时更新画像与实体信任度；默认关闭、可一键清除 | `diting/watcher/` |
| 🎯 **避毒推荐引擎** | 内容相似度 + 隐式反馈协同过滤，叠加 GEO 安全门：虚假评论/刷屏水军/恶意商家降权并说明理由 | `diting/recommend/` |
| 🔀 **中转站兼容修复** | 诊断并修复部分 OpenAI 兼容中转站（如 micuapi.ai）因 301 重定向丢鉴权头而不可用的问题；`relay doctor` 一键体检 | `diting/relay/` + `plugins/model-providers/custom/` |
| 📊 **回测框架** | 合成对抗语料回测：三档混淆矩阵、话术 Recall@5、多源共振检出、推荐避毒验证 | `diting/backtest/` |
| 🖥️ **桌面版（Electron）** | 谛听品牌的原生桌面窗口：对话/会话/技能/模型配置 + 专属「画像与长程记忆」面板（可视化增删改 USER.md/MEMORY.md、兴趣信号、授权、长任务，附等效命令提示） | `apps/desktop/` + `hermes_cli/web_routers/diting.py` |
| 🧠 **画像与记忆命令** | `hermes diting profile/memory` 查看与修改用户画像（USER.md）和长程记忆（MEMORY.md）；`hermes diting help` 输出命令全览，CLI/桌面版/对话三入口同一份数据 | `plugins/diting_guard/profile_memory.py` |
| 🧬 **技能自进化** | vendor 自 NousResearch/hermes-agent-self-evolution（MIT）：DSPy+GEPA 反思式进化优化技能，约束门全保留，产物仅供人工评审绝不自动落库 | `evolution/` |

Hermes 原有能力全部保留：多平台网关（Telegram/Discord/Slack/WhatsApp/CLI/TUI）、
桌面端、自我改进技能系统、cron 定时任务、子代理并行等。

## 快速开始（Windows）

```bash
# 0. 生成桌面图标：「谛听 Diting」= CLI，「谛听 Diting 桌面版」= Electron 窗口
#    （首启自动建 venv+装依赖+建库；桌面版首启自动构建前端资产）
powershell -ExecutionPolicy Bypass -File scripts\make_desktop_shortcut.ps1

# 1. 安装（要求 Python 3.11–3.14；内部包名沿用 hermes-agent 以保线协议兼容）
pip install -e .

# 2. 构建 GEO 甄别种子知识库（66 条，幂等可重跑）
python -m diting.geo_guard.ingest --seed

# 3. 启动 —— 两种入口等价
diting            # 谛听品牌入口
hermes            # 上游入口

# 4. 无 LLM 也能跑：甄别内核全链路规则降级
python -m diting.backtest.run          # 回测 + 报告

# 5. 画像与长程记忆（CLI/桌面版/对话三入口同一份数据）
hermes diting help                     # 命令全览（全部提示都在这）
hermes diting profile                  # 查看用户画像（USER.md + 兴趣信号 + 授权）
hermes diting profile add 偏好简体中文回复
hermes diting memory                   # 查看长程记忆（MEMORY.md）
hermes diting memory add 项目仓库在 Desktop/diting-agent

# 6. 桌面版（Electron 原生窗口）
hermes desktop --source                # 或双击「谛听 Diting 桌面版」图标
```

### 对话中使用（插件工具）

对话内工具由 `diting_guard` 插件提供，默认关闭；首次使用启用一次
（`hermes diting …` 终端命令与桌面画像/记忆面板不依赖此开关，开箱即用）：

```bash
hermes plugins enable diting-guard
```

配置好任意模型后，直接在对话里说：

```
帮我甄别这篇「2026十大空气净化器排行榜」……（粘贴文本）
这条 AI 推荐回答可信吗？来源是这三个链接……
买到了虚假宣传的商品怎么维权？
推荐一款靠谱的空气净化器     ← 走避毒推荐链路
我之前查过清澜吗？           ← 长期记忆召回
```

## 中转站（OpenAI 兼容 relay）配置

国内中转站常见三大坑，`relay doctor` 一次体检全部给出结论与修复建议：

```bash
python -m diting.relay doctor https://micuapi.ai/v1 --api-key sk-xxx
```

| 症状 | 根因 | 修复 |
|---|---|---|
| 401 Invalid token | 裸域 301 → `www.` 子域，重定向跨域时鉴权头被剥离 | doctor 自动给出重定向后的最终 URL，填入 `model.base_url` |
| DNS 解析失败 | 猜的 `api.` 子域不存在 | doctor 探测真实端点 |
| 模型列表为空 | `/v1/models` 探测失败 → 选择器无候选 | 手动输入模型名，或 `api_mode: chat_completions` 强制走通用链路 |

修复后的 custom provider 会在探测时**自动解析重定向**，配置 `https://micuapi.ai/v1`
也能正常工作（见 `plugins/model-providers/custom/`）。

## 隐私红线

- 浏览画像**默认关闭**，需显式授权（`browse_consent` 工具或 `diting consent` 命令），授权记录含时间戳可审计
- 只存聚合信号与被标记域名，不存完整浏览历史；全部本地 SQLite，不上云
- `forget` / `export` 一键删除或导出个人数据
- 用户画像**永不影响**风险判定分数（只调制呈现方式）——判定公正性红线
- 知识库仅做防御视角抽象，不含可操作的投毒方法

## 项目结构

```
diting/                    # 谛听创新层（本项目全部新增代码）
├── geo_guard/             #   GEO 逆向甄别内核（vendored，97 项测试）
├── recommend/             #   避毒推荐引擎
├── watcher/               #   授权制浏览画像
├── longtask/              #   长任务记忆
├── relay/                 #   中转站诊断与修复
├── backtest/              #   回测框架（六段式验收）
└── tests/                 #   121 项测试（97 内核 + 24 谛听模块/集成）
plugins/diting_guard/      # Hermes 插件：13 工具 + diting CLI + 会话钩子
│                          #   + profile_memory.py（画像/记忆共享 handler）
plugins/model-providers/custom/  # 中转站兼容修复（上游插件内修改）
evolution/                 # 技能自进化（vendor 自 hermes-agent-self-evolution，MIT）
apps/desktop/              # 谛听桌面版（Electron，品牌化自上游桌面壳）
hermes_cli/web_routers/diting.py  # 桌面端画像/记忆 API（/api/diting/*）
docs/                      # 使用手册 + 防投毒白皮书 + 上游 README 归属保留
```

- 📖 **[使用手册](docs/DITING_GUIDE.md)** —— 安装、中转站配置、对话工具、CLI、授权与隐私
- 🛡️ **[GEO 防投毒七层防线白皮书](docs/ANTI_POISONING.md)** —— 每层防什么、怎么防、回测证据
- 架构决策与数据契约见上游内核仓库
  [platform-financial-agent](https://github.com/Fishman-free/platform-financial-agent)
  （docs/00~07 设计文档 + openspec 六能力 39 条规格）

## 回测

```bash
python -m diting.backtest.run --report BACKTEST_REPORT.md
```

输出：三档风险混淆矩阵、话术 Recall@5、注入检出率、多源共振/反证缺失检出、
推荐避毒命中率、relay doctor 自检。最近一次结果（[BACKTEST_REPORT.md](BACKTEST_REPORT.md)）：
**验收阈值 9/9 通过**，注入检出 100%、软文 ≥MEDIUM 100%、良性误报 0/8、Recall@5 = 1.00。
合成对抗语料仅内部评测，不入库不外发。

## 许可与归属

MIT。本产品基于 Nous Research 的 Hermes Agent（MIT）修改，
`evolution/` vendor 自 Nous Research 的
[hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)
（MIT，溯源与补丁清单见 [evolution/VENDOR.md](evolution/VENDOR.md)）。
完整归属与修改清单见 [NOTICE](NOTICE)。感谢 Nous Research 开源了如此优秀的 Agent 框架。

桌面版借鉴 [Hermes-CN-Desktop](https://github.com/Eynzof/Hermes-CN-Desktop)（PolyForm NC）
的产品形态，**未使用其任何代码**——桌面壳来自本仓库 MIT 上游自带的 `apps/desktop/`。

引用了 K-Dense Scientific Agent Skills 的结构化头脑风暴方法（arXiv:2609.00065）。
