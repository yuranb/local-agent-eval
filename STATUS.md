# STATUS.md

最后更新：2026-10-05（夜间自主工作会话）

## 完成了什么

| 范围项 | 状态 | 备注 |
|---|---|---|
| 1. 选模型 | **部分完成** | 默认值定为 `qwen2.5:7b` 并写入 DECISIONS.md D2，但本机没有 Ollama，无法 `ollama list` 验证或 pull，未经过真实验证 |
| 2. 三个本地工具 | 完成 | `agent/tools.py`：search_docs（docs/ 内检索）、calculator（ast 白名单）、add_workdays（跳过周末，支持负数/0）。docs/ 实际放了 **11** 篇公有领域文本（要求 ≥10），来源与许可见 docs/SOURCES.md |
| 3. FastAPI POST /chat | 完成 | 返回最终答案、每次工具调用的名字/参数/结果、步数、错误、实测延迟毫秒数。后端可注入 |
| 4. 评估集 50 条 | 完成 | 15 search + 12 calculator + 13 add_workdays + 10 no_tool（≥10 条不用工具 ✓）。AI 起草、**尚未人工审核**（README 已如实标注） |
| 5. 评估脚本 | 完成 | 三个准确率 + P50/P95（线性插值法），结果 JSON 落盘 |
| 6. pytest | 完成 | **106 个测试，106 通过 / 0 失败**；评估脚本测试用 stub 模型和录制回放，不碰 Ollama |
| 7. GitHub Actions | 完成（未实跑） | `test` job 跑 pytest；`eval-gate` job 跑录制评估 + 门禁对比。**workflow 文件未在真实 GitHub Actions 上执行过**（规则禁止创建远程仓库/push），YAML 语法已本地校验 |
| 8. Dockerfile | 完成（未验证） | python:3.12-slim + uvicorn。**本机没有 Docker，未验证 build**，按规则在 README 和此处标注"未验证" |
| 9. 真实结果 | **未完成** | 本机没有 Ollama，50 条用例的真实模型运行没有做。README 有真实结果表的只有：106 个测试、fixture 评估指标（含义已标注）、API 无 Ollama 时的实测响应 |

## 没完成什么 / 卡在哪里

1. **Ollama 不存在**（`which ollama`、`/usr/local/bin/ollama`、
   `/opt/homebrew/bin/ollama`、`/Applications/Ollama.app` 均无）。按规则
   "不要安装"，所以：模型未下载、`evals/record.py` 从未执行、范围 9 无数字。
   卡点解除方式：装好 Ollama 后依次跑
   `ollama pull qwen2.5:7b` → `python -m evals.record` →
   `python -m evals.run_eval --backend recording --out evals/baseline.json`。
2. **Docker 不存在**，Dockerfile 无法 build 验证 → **未验证**。
3. **GitHub Actions 无法实跑**（规则禁止 push / 创建远程仓库）→ workflow
   只做了语法校验，未验证。
4. **用例未人工审核**：50 条用例是 AI 起草的，机器一致性测试全过，但项目
   所有者醒来后应人工过一遍（尤其 search-003 这类曾因折行修过期望查询的）。

## 测试

- 命令：`.venv/bin/python -m pytest tests/ -q`
- 结果：**106 passed, 0 failed**（2026-10-05 实际输出）
- 分布：test_tools 37 / test_scoring 19 / test_eval_pipeline 16 /
  test_eval_dataset 10 / test_llm 9 / test_loop 8 / test_app 7
- 其中评估管线测试全程使用 stub / fixture，不调用 Ollama。

## 真实结果表

### 评估指标（fixture 录制，来源 evals/baseline.json）

| 指标 | 值 |
|---|---|
| total_cases | 50 |
| tool_selection_accuracy | 1.000 |
| argument_accuracy | 1.000 |
| answer_accuracy | 1.000 |
| latency P50 / P95 (ms) | 0.0 / 0.0 |

**含义必须读清楚**：录制是 `evals/make_recordings.py` 生成的理想轨迹，
不是真实模型响应（DECISIONS.md D3）。这组数字验证的是评测管线自身
（循环、工具分发、打分、门禁）没有回归；**不代表任何模型能力**。

### API 实测（无 Ollama 环境下本机 curl）

| 请求 | 响应 |
|---|---|
| GET /health | 200 `{"status":"ok"}` |
| POST /chat（正常问题） | 200，`error: "cannot reach Ollama at http://localhost:11434 — …"`，`latency_ms: 37` |
| POST /chat（空 question） | 422 |

### 真实模型评估

无。不编造。

## 提交历史（本地 git，未 push）

每完成一个范围项小步提交一次，全程未 push、未建远程仓库；
`git log --oneline` 可查。
