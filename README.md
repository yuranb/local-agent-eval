# local-agent-eval

一个完全跑在笔记本上的 AI 助手：用本机 Ollama 的小模型（qwen2.5:7b）通过
tool calling 完成任务（搜索本地文档、算术、工作日日期计算），带一套 50 条
用例的评估，评估接进 GitHub Actions 作为回归门禁。

**状态：全范围完成。50 条用例已用真实模型跑完，数字在下表；Docker build 和
GitHub Actions 实跑仍未验证（本机无 Docker、未建远程仓库），详见
[STATUS.md](STATUS.md)。**

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 跑全部单元测试（不依赖 Ollama）
.venv/bin/python -m pytest tests/ -q

# 用真实 Ollama 跑评估（约 30 分钟，50 条 × 多轮推理）
.venv/bin/python -m evals.run_eval --backend ollama --out evals/results.json

# 用录制回放跑评估 + 门禁（秒级，CI 里就是这么跑的）
.venv/bin/python -m evals.run_eval --backend recording --out evals/results.json
.venv/bin/python -m evals.gate --results evals/results.json --baseline evals/baseline.json

# 重新录制真实模型响应（改 prompt / 换模型后执行，再重建 baseline）
.venv/bin/python -m evals.record --model qwen2.5:7b

# 起 API
.venv/bin/python -m uvicorn server.app:app --port 8000
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
     -d '{"question": "What is 12*12?"}'
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
      │              evals/gate.py ◄── evals/baseline.json（真实录制回放）
      ▼
.github/workflows/ci.yml：pytest job + 评估门禁 job
```

模型后端可插拔：`OllamaBackend`（真实）、`RecordingBackend`（回放真实录制）、
测试用 stub，三者走同一个 `agent/loop.py`。

## 真实结果

环境：Ollama 0.35.1，qwen2.5:7b（7.6B，Q4_K_M），macOS 笔记本，
2026-10-05。每一个数字都来自实际执行的脚本输出，出处标注在"来源"列。

### 真实模型评估（来源：`evals/results.json`，由
`python -m evals.run_eval --backend ollama` 于 2026-10-05T17:28Z 生成）

| 指标 | 值 | 含义 |
|---|---|---|
| total_cases | 50 | 全部跑完 |
| tool_selection_accuracy | 0.920 | 46/50 调对了工具集合 |
| argument_accuracy | 0.525 | 21/40（分母只算有期望参数的 40 条） |
| answer_accuracy | 0.740 | 37/50 最终答案过判定规则 |
| latency P50 / P95 | 10 845 / 20 818 ms | 单条用例整循环耗时 |

**必须知道的三个注脚**：

1. **两条基础设施失败**：workday-001（一轮推理超过 900 秒超时）、
   workday-005（Ollama 返回 HTTP 500）。跑评测时同一台 Ollama 服务器上
   还有另一个本地项目的评测进程在并发请求（见 DECISIONS.md D11），这两条
   是环境失败而非模型失败——同两条在录制 pass 中均正常完成。按"不重跑、
   不挑数字"的原则如实计入。
2. **运行间方差**：另一条独立 pass（录制回放，见下）测得
   0.960 / 0.575 / 0.820。两次运行差 2–8 个百分点，是 7B 模型的真实
   随机性；单次评估的绝对值别太当真，看趋势要看多次。
3. **P95 对离群值稳健**：去掉 900 秒那条后 P95 为 19 087 ms，
   差异很小（线性插值分位数的性质）。

### 失败模式分析（来源：`evals/results.json` 与 `evals/recordings/` 的逐条记录）

| 模式 | 证据 | 解读 |
|---|---|---|
| search 参数 15/15 全不中 | 模型改写查询词，如期望 `four score and seven`、实际 `Gettysburg Address first words` | 期望参数是"我理想中的查询"，模型有自己合理的写法；严格匹配故意暴露这个差异 |
| search 答案 8 条不中 | 查询词弱时检索返回标题行（如 search-001 返回 "The Gettysburg Address" 而非正文） | 词面匹配检索的上限；升级路径是 BM25/向量检索 |
| workday 真实算错 | workday-006 发了 `days: -2`（期望 -1），答案因此错成 10-08 | 7B 模型对"1 个工作日之前"的真实理解错误，正是这类评测要抓的 |
| 不该调工具时调了 | notool-005（"谁写了 Hamlet"）两次运行都去调 search_docs，但最终答案仍正确（Shakespeare 不在语料里，模型自己知道） | 工具选择和答案正确性是两个独立维度，一个可以对另一个错 |
| 答案拼错词 | notool-006 答出 "portunese"（Portuguese） | 7B 量化模型的真实短板，没有任何后台逻辑能救 |
| 重复调用工具 | calc-004 同一轮连调两次 calculator | 工具选择指标是**严格列表相等**，重复调用算失败——故意的，见 DECISIONS.md D12 |

### 门禁基线（来源：`evals/baseline.json`，由
`python -m evals.run_eval --backend recording` 在真实录制上生成）

| 指标 | 值 |
|---|---|
| tool_selection_accuracy | 0.960 |
| argument_accuracy | 0.575 |
| answer_accuracy | 0.820 |

基线 = 回放 `evals/recordings/`（qwen2.5:7b 的真实响应，模型侧逐字重放、
工具真实执行），所以是确定性的：CI 上重放同一批录制，指标恒等于基线，
除非管线代码（工具/打分/循环）被改坏——这就是门禁抓的回归。
换模型或改 prompt 后：`evals/record.py` 重录 → 重建 baseline → 门禁
升级为新一轮的模型回归门禁。

### Pipeline self-test（管线自检，历史 fixture 数据）

fixture 录制（脚本生成的"理想模型轨迹"，非任何真实模型输出）曾用于
CI 门禁的第一个版本，当时的评估结果是三个准确率全部 1.000、延迟
0/0 ms。**它的含义**：理想轨迹下管线端到端得分 100%，证明循环、工具
分发、打分、指标计算这一套机器是自洽的；它从未代表模型能力。现在
`evals/recordings/` 已被真实录制覆盖，这套自检保留在
`tests/test_eval_pipeline.py::test_run_eval_recording_backend_perfect_on_fixtures`
（在临时目录现场生成 fixture 再跑全量 50 条）和
`python -m evals.make_recordings.py`（可随时重新生成 fixture）里。

### 单元测试（来源：`pytest tests/ -q` 实际输出，109 通过 / 0 失败）

| 测试文件 | 用例数 | 结果 |
|---|---|---|
| tests/test_tools.py | 37 | 全部通过 |
| tests/test_scoring.py | 21 | 全部通过 |
| tests/test_eval_pipeline.py | 16 | 全部通过 |
| tests/test_eval_dataset.py | 10 | 全部通过 |
| tests/test_llm.py | 10 | 全部通过 |
| tests/test_loop.py | 8 | 全部通过 |
| tests/test_app.py | 7 | 全部通过 |
| **合计** | **109** | **109 通过 / 0 失败** |

### API 实测（2026-10-05，本机 `uvicorn` + `curl`）

| 请求 | 实际响应 |
|---|---|
| `GET /health` | `200`，`{"status":"ok"}` |
| `POST /chat`（无 Ollama 时） | `200`，`error:"cannot reach Ollama at http://localhost:11434 — ..."`，`latency_ms:37` |
| `POST /chat`（question 全空格） | `422`（pydantic 校验拒绝） |

## 评测集

`evals/cases.jsonl`，共 50 条：

| 类别 | 数量 | 说明 |
|---|---|---|
| search_docs | 15 | 每题对应 docs/ 里一篇文章的一个可检索事实 |
| calculator | 12 | 算术题，期望参数含完整表达式 |
| add_workdays | 13 | 工作日日期计算（含负数、跨周末、0 天） |
| no_tool | 10 | 不需要任何工具的常识问答（≥10 条的要求由此满足） |

每条包含：`question`、`expected_tools`、`expected_args`（按工具分组、
子集匹配、数值/字符串归一化且**忽略格式空白**——`744 / 8` 等于
`744/8`，但词序和选词不同照样失败）、`answer_rule`（`contains` 或
`regex`，大小写不敏感）。

**用例来源说明**：50 条用例由 AI（Claude Code）起草，由项目所有者负责
审核；截至 2026-10-05 尚未人工复核，`tests/test_eval_dataset.py` 里的
一致性测试（期望参数真实可执行、答案规则与真实工具输出匹配）是目前的
机器校验防线。

## 设计决定

全部记录在 [DECISIONS.md](DECISIONS.md)，重点：

- D2/D10：模型 `qwen2.5:7b`（7.6B、原生 tool calling、Apache-2.0、双语），
  先定为默认值、后经真实运行证实可用；`OLLAMA_MODEL` 可换。
- D3/D10：CI 门禁回放录制响应；录制已从 fixture 升级为真实模型响应。
- D4：门禁只比较三个准确率，不比较延迟（跨机器延迟不可比）。
- D11：评测期间共享 Ollama 服务器的并发影响与两条环境失败的出处。
- D12：参数比较忽略格式空白；工具选择严格列表相等（重复调用算失败）。

## 目录结构

```
docs/               11 篇公有领域语料 + SOURCES.md（来源与许可）
agent/tools.py      三个本地工具 + JSON schema + 分发
agent/loop.py       模型↔工具循环（项目核心）
agent/llm.py        Ollama HTTP 客户端 + 消息归一化 + 错误翻译
agent/config.py     模型/host/max_steps/超时配置（环境变量可覆盖）
server/app.py       FastAPI POST /chat
evals/cases.jsonl   50 条评估用例
evals/scoring.py    纯打分逻辑（工具选择/参数/答案/百分位）
evals/run_eval.py   评估入口（recording | ollama 两种后端）
evals/recordings/   50 份真实模型录制（qwen2.5:7b，2026-10-05）
evals/make_recordings.py  生成 fixture（自检/教学用，非真实数据）
evals/record.py     用真实 Ollama 重录
evals/baseline.json 门禁基线（真实录制回放的真实输出）
evals/gate.py       门禁：低于基线即退出码 1
tests/              109 个测试
.github/workflows/ci.yml   pytest job + 评估门禁 job
Dockerfile          API 容器（本机无 Docker，未验证 build）
```
