# evolution/ — vendored hermes-agent-self-evolution

来源：[NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)
上游 commit：`0a929e3aa20e15cf04dc7c28492a7d41a5139125`（2026-06-17）
许可证：**MIT**（© 2026 Nous Research），归属同步记录于仓库根 `NOTICE`。

用 DSPy + GEPA（Genetic-Pareto 提示进化，ICLR 2026 Oral）对 Hermes/谛听的技能文件
（SKILL.md）做反思式进化优化：读取执行轨迹 → 生成评测集 → 变异候选 → 约束门
（测试/尺寸/语义保持）→ 输出最优变体。纯 API 调用，无需 GPU 训练。

## 目录对照（相对上游）

| 上游路径 | 本仓库路径 | 说明 |
| --- | --- | --- |
| `evolution/` | `evolution/` | 包本体，**导入路径零改动** |
| `tests/` | `evolution/tests/` | 移入包内，避免根 `pytest`（testpaths=tests）误采集 |
| `datasets/` | `evolution/datasets/` | golden 数据集占位 |
| `reports/` | `evolution/reports/` | 上游 Phase 1 验证报告 PDF |
| `generate_report.py` | `evolution/generate_report.py` | 报告生成器（需 reportlab，惰性工具） |
| `README.md` | `evolution/README.upstream.md` | 上游 README 原样保留 |
| `PLAN.md` | `evolution/PLAN.md` | 上游完整架构规划 |

## 本地补丁（均以 `[diting patch]` 注释标记）

1. `evolution/core/config.py` — `get_hermes_agent_path()` 新增第 2 优先级：
   evolution/ 被 vendor 在 hermes-agent fork 内部时，包的祖父目录即 repo 本体，
   免设 `HERMES_AGENT_REPO` 即可自发现。
2. `evolution/core/external_importers.py` — `HermesSessionImporter.SESSION_DIR`
   尊重 `HERMES_HOME` 环境变量（谛听运行时的会话可能不在 `~/.hermes` 下）。
3. `evolution/tests/core/test_config_repo_path.py` — 随补丁 1 调整
   `test_config_constructs_without_repo` 断言（fork 内 own-root 恒可发现，
   不再是 None）；`test_resolve_expands_user_home` 加 win32 skip
   （Windows expanduser 用 USERPROFILE 不认 HOME，环境性差异，非补丁回归）。

## 运行

```bash
# 依赖为可选 extra（dspy + click；openai/pyyaml/rich 主包已含）
uv pip install -e ".[evolution]"        # 或 pip install "dspy>=3.0" click

# 模型 API key 仅走环境变量（dspy.LM 经 LiteLLM）：OPENAI_API_KEY / OPENROUTER_API_KEY 等
export OPENAI_API_KEY=...

# 方式一：谛听 CLI 包装（推荐，默认 repo=本仓库）
hermes diting evolve skill <技能名> --iterations 10 --eval-source synthetic

# 方式二：上游原生命令
python -m evolution.skills.evolve_skill --skill <技能名> --iterations 10
```

评测数据源：`synthetic`（LLM 合成）/ `golden`（evolution/datasets/ 下 JSONL）/
`sessiondb`（挖掘本机 Claude Code、Copilot、Hermes 历史会话）。

约束门（上游 Guardrails 原样生效）：pytest 全绿、技能 ≤15KB、工具描述 ≤500 字符、
禁止会话中途变更、语义不漂移；进化产物默认走 PR 人工评审，**绝不直接落库**。

## vendor 测试

```bash
uv pip install -e ".[evolution]" && python -m pytest evolution/tests -q
```

仓库根的 `diting/tests/test_evolution_vendor.py` 不依赖 dspy，做零依赖冒烟
（溯源标记、repo 自发现、CLI 缺依赖时的安装提示）。
