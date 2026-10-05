# local-agent-eval

一个完全跑在笔记本上的 AI 助手：用本机 Ollama 的小模型通过 tool calling
完成任务（搜索本地文档、算术、工作日日期计算），带一套 50 条用例的评估，
评估接进 GitHub Actions 作为回归门禁。

**当前状态：代码和测试全部完成并通过；本机没有安装 Ollama，所以"真实模型"
部分的数字是空的——没有编造。** 详见 [STATUS.md](STATUS.md)。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 跑全部单元测试（不依赖 Ollama）
.venv/bin/python -m pytest tests/ -q

# 用录制好的模型响应跑评估（不依赖 Ollama；当前是 fixture，见下文）
.venv/bin/python -m evals.run_eval --backend recording --out evals/results.json

# 对比基线（CI 门禁同一入口）
.venv/bin/python -m evals.gate --results evals/results.json --baseline evals/baseline.json

# 起 API
.venv/bin/python -m uvicorn server.app:app --port 8000
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
     -d '{"question": "What is 12*12?"}'
```

装好 Ollama 之后的真实模型路径（本机未执行过）：

```bash
.venv/bin/python -m evals.record --model qwen2.5:7b        # 录制真实模型响应
.venv/bin/python -m evals.run_eval --backend ollama --out evals/results.json
```

## 数据流

```
docs/*.txt (11 篇公有领域文本)
      │
      ▼
agent/tools.py  ←─ search_docs / calculator / add_workdays（全部本地，无网络）
      │                        ▲
      ▼                        │ 工具结果回传
agent/loop.py  agent/llm.py ── Ollama /api/chat（localhost:11434）
      │
      ▼
server/app.py  ← POST /chat：最终答案 + 每次工具调用的参数和结果
      │
      ▼
evals/cases.jsonl (50 条用例)
      │
      ▼
evals/run_eval.py ──► results JSON（三个准确率 + P50/P95 延迟）
      │                    │
      │                    ▼
      │              evals/gate.py ◄── evals/baseline.json
      ▼
.github/workflows/ci.yml：pytest job + 评估门禁 job
```

模型后端可插拔：`OllamaBackend`（真实）、`RecordingBackend`（回放录制）、
测试用 stub，三者走同一个 `agent/loop.py`。

## 真实结果

以下每一个数字都来自本机实际执行（2026-10-05，Python 3.14.7，macOS），
出处标注在"来源"列。

### 单元测试（来源：`pytest tests/ -q` 实际输出）

| 测试文件 | 用例数 | 结果 |
|---|---|---|
| tests/test_tools.py | 37 | 全部通过 |
| tests/test_scoring.py | 19 | 全部通过 |
| tests/test_eval_pipeline.py | 16 | 全部通过 |
| tests/test_eval_dataset.py | 10 | 全部通过 |
| tests/test_llm.py | 9 | 全部通过 |
| tests/test_loop.py | 8 | 全部通过 |
| tests/test_app.py | 7 | 全部通过 |
| **合计** | **106** | **106 通过 / 0 失败** |

### 评估指标（来源：`evals/baseline.json`，由
`python -m evals.run_eval --backend recording --out evals/baseline.json` 生成）

| 指标 | 值 | 说明 |
|---|---|---|
| total_cases | 50 | 用例总数 |
| tool_selection_accuracy | 1.000 | fixture 理想轨迹下的管线自检 |
| argument_accuracy | 1.000 | 同上 |
| answer_accuracy | 1.000 | 同上 |
| latency P50 / P95 | 0 / 0 ms | 回放后端不做模型推理，延迟无意义，仅格式占位 |

**这组 1.000 不代表任何模型能力**：录制文件是脚本生成的"理想模型"轨迹
（`evals/recordings/*.json`，`source: fixture`），工具是真实执行的，模型侧
是脚本。它验证的是评测管线本身；装上 Ollama 后用 `evals/record.py` 重录，
同一套管线立刻升级为真实模型门禁。

### API 实测（来源：本机 `uvicorn` + `curl`，无 Ollama 环境）

| 请求 | 实际响应 |
|---|---|
| `GET /health` | `200`，`{"status":"ok"}` |
| `POST /chat`（正常问题） | `200`，`answer:""`，`error:"cannot reach Ollama at http://localhost:11434 — ..."`，`latency_ms:37` |
| `POST /chat`（question 全空格） | `422`（pydantic 校验拒绝） |

### 真实模型结果：**无**

本机没有 Ollama（`which ollama` 及常见安装路径均未找到），按规则不安装、
不编造。范围 9 的"50 条用例真实跑完"**未完成**，此表留空即为真实状态。

## 评测集

`evals/cases.jsonl`，共 50 条：

| 类别 | 数量 | 说明 |
|---|---|---|
| search_docs | 15 | 每题对应 docs/ 里一篇文章的一个可检索事实 |
| calculator | 12 | 算术题，期望参数含完整表达式 |
| add_workdays | 13 | 工作日日期计算（含负数、跨周末、0 天） |
| no_tool | 10 | 不需要任何工具的常识问答（≥10 条的要求由此满足） |

每条包含：`question`、`expected_tools`、`expected_args`（按工具分组、
支持子集匹配和数值/字符串归一化比较）、`answer_rule`（`contains` 或
`regex`，大小写不敏感）。

**用例来源说明**：50 条用例由 AI（Claude Code）起草，由项目所有者负责
审核；截至 2026-10-05 尚未人工复核，`tests/test_eval_dataset.py` 里的
一致性测试（期望参数真实可执行、答案规则与真实工具输出匹配）是目前的
机器校验防线。

## 设计决定

全部记录在 [DECISIONS.md](DECISIONS.md)，重点：

- D2：模型默认 `qwen2.5:7b`（7.6B、原生 tool calling、Apache-2.0、中英双语），
  本机无 Ollama，**未经验证**，环境变量 `OLLAMA_MODEL` 可换。
- D3：CI 门禁用录制响应回放；当前录制是 fixture（理想轨迹），含义与升级
  路径见上文。
- D4：门禁只比较三个准确率，不比较延迟（跨机器延迟不可比）。
- D8：工具失败变成 `{"error": ...}` 观察结果回传模型，不让循环崩溃。

## 目录结构

```
docs/               11 篇公有领域语料 + SOURCES.md（来源与许可）
agent/tools.py      三个本地工具 + JSON schema + 分发
agent/loop.py       模型↔工具循环（项目核心）
agent/llm.py        Ollama HTTP 客户端 + 消息归一化
agent/config.py     模型/host/max_steps 配置（环境变量可覆盖）
server/app.py       FastAPI POST /chat
evals/cases.jsonl   50 条评估用例
evals/scoring.py    纯打分逻辑（工具选择/参数/答案/百分位）
evals/run_eval.py   评估入口（recording | ollama 两种后端）
evals/recordings/   50 份录制（当前为 fixture）
evals/make_recordings.py  从 cases.jsonl 生成 fixture
evals/record.py     用真实 Ollama 重录（本机未执行过）
evals/baseline.json 门禁基线（recording 跑出的真实输出）
evals/gate.py       门禁：低于基线即退出码 1
tests/              106 个测试
.github/workflows/ci.yml   pytest job + 评估门禁 job
Dockerfile          API 容器（本机无 Docker，未验证 build）
```
