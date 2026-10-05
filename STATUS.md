# STATUS.md

最后更新：2026-10-05（白天会话，真实模型已接入）

## 完成了什么

| 范围项 | 状态 | 备注 |
|---|---|---|
| 1. 选模型 | 完成 | `qwen2.5:7b`（7.6B，Q4_K_M），Ollama 0.35.1 实测可用，与 DECISIONS.md D2 预定值一致 |
| 2. 三个本地工具 | 完成 | `agent/tools.py`：search_docs、calculator（ast 白名单）、add_workdays。docs/ 11 篇公有领域文本（要求 ≥10），来源见 docs/SOURCES.md |
| 3. FastAPI POST /chat | 完成 | 返回答案 + 每次工具调用的名字/参数/结果 + 步数 + 实测延迟。后端可注入 |
| 4. 评估集 50 条 | 完成 | 15 search + 12 calculator + 13 add_workdays + 10 no_tool。AI 起草、**尚未人工审核**（README 已如实标注） |
| 5. 评估脚本 | 完成 | 三个准确率 + P50/P95（线性插值），结果 JSON 落盘；参数比较忽略格式空白（D12） |
| 6. pytest | 完成 | **109 个测试，109 通过 / 0 失败**；评估管线测试用 stub/fixture，不依赖 Ollama |
| 7. GitHub Actions | 完成（未实跑） | `test` job + `eval-gate` job（录制回放 + 门禁）。**未在真实 GitHub Actions 上执行过**（未建远程仓库/push），YAML 已本地语法校验 |
| 8. Dockerfile | 完成（未验证） | python:3.12-slim + uvicorn。**本机没有 Docker，未验证 build** |
| 9. 真实结果 | **完成** | 50/50 条用真实 qwen2.5:7b 跑完两次（录制 pass + live pass），数字在下方真实结果表 |

## 解锁步骤执行记录（2026-10-05 上午）

1. `ollama list` 确认 qwen2.5:7b（4.7 GB，Q4_K_M）已下载。
2. `python -m evals.record --model qwen2.5:7b` → **50/50 条录制成功，退出码
   0（没有任何一条以循环错误结束）**。真实录制已覆盖 `evals/recordings/`
   （fixture 可用 `make_recordings.py` 重新生成，旧版在 git 历史）。
3. `python -m evals.run_eval --backend recording --out evals/baseline.json`
   → 门禁基线重建为真实录制回放值：0.960 / 0.575 / 0.820。
4. `python -m evals.run_eval --backend ollama --out evals/results.json`
   → live 全量评测，含真实延迟。（首次运行受另一进程争抢影响，见下文
   环境告警；服务器空闲后重跑至 `evals/results_live.json` 并提交，
   README/STATUS 采用重跑数字。）

## 没完成什么 / 卡在哪里

1. **Dockerfile 未验证 build**：本机无 Docker。
2. **GitHub Actions 未实跑**：未建远程仓库（规则禁止 push）。本地已模拟
   CI 门禁路径：recording 评估 + gate 退出码 0。
3. **用例未人工审核**：50 条仍是 AI 起草 + 机器一致性校验，建议人工过一遍。
4. **环境告警（已解除，留档）**：第一次 live 评测期间同一台 Ollama 服务器
   上有另一个项目的评测进程并发请求（DECISIONS.md D11），产生两条环境失败
   和虚高延迟。该进程结束后，已确认服务器空闲并**重跑 live 评测**
   （evals/results_live.json，零环境失败），README/STATUS 均已改用这次
   干净运行的数字。第一次的数字未再引用。

## 测试

- 命令：`.venv/bin/python -m pytest tests/ -q`
- 结果：**109 passed, 0 failed**（2026-10-05 实际输出）
- 分布：test_tools 37 / test_scoring 21 / test_eval_pipeline 16 /
  test_eval_dataset 10 / test_llm 10 / test_loop 8 / test_app 7

## 真实结果表

### Live 全量评测（qwen2.5:7b，来源 evals/results_live.json，2026-10-05T18:29:47Z）

启动前确认服务器空闲（`/api/ps` 无已加载模型、无其他连接），零错误、
零环境失败。结果文件已提交进 git，作为 README 数字的可追溯来源。

| 指标 | 值 |
|---|---|
| total_cases | 50 |
| tool_selection_accuracy | 0.940 |
| argument_accuracy | 0.550（分母 40） |
| answer_accuracy | 0.820 |
| latency P50 / P95 (ms) | 5 975 / 16 536 |

P95 去掉 workday-008 离群值（该条单轮连调 97 次工具，耗时 700 秒）后
为 16 080 ms，几乎不变。

### 参数准确率按工具分解（同一次运行）

| 工具 | 正确率 | 说明 |
|---|---|---|
| search_docs | 0/15 | 评分要求查询词与期望**逐字一致**（忽略大小写和空白后仍需同词同序）；模型每次都改写查询词，故全部判不中。是评分口径的严格性：15 条中 9 条最终答案仍正确 |
| calculator | 10/12 | calc-005 词序不同（`240 * 0.15` vs `0.15*240`）；calc-012 没调工具直接答对 |
| add_workdays | 12/13 | workday-006 发 `days: -2`（期望 -1），真实的理解错误 |

### 门禁基线（真实录制回放，来源 evals/baseline.json）

| 指标 | 值 |
|---|---|
| tool_selection_accuracy | 0.960 |
| argument_accuracy | 0.575（分母 40） |
| answer_accuracy | 0.820 |

两次独立 pass 差 2–8 个百分点 = 7B 模型的真实运行间方差。
门禁在 CI 里回放同一批录制，是确定性的：只有管线代码被改坏才会掉到
基线之下。

### 失败模式（来源 evals/results_live.json，详见 README 的失败模式分析表）

- search 参数 0/15：查询词需与期望逐字一致，模型每次都改写（评分口径严格）；
  但 search 的最终答案 9/15 正确。
- workday-008：单轮连调 97 次 add_workdays，答案仍对，耗时 700 秒。
- calc-012：没调 calculator 直接心算答对（答案对、策略错）。
- workday-006：两次 live 运行都发 `days: -2`（期望 -1）→ 稳定的模型理解错误。
- notool-005：三次运行（录制 + 两次 live）都不该调工具却调了 search_docs，
  但答案仍对。

### Pipeline 自检（历史 fixture 数据，含义见 README 专门小节）

fixture 理想轨迹下三个准确率 1.000、延迟 0/0 ms——证明管线自洽，
不代表模型能力。现保留于 test_eval_pipeline 的临时 fixture 测试与
`make_recordings.py`。

## 提交历史（本地 git，未 push）

每完成一步小步提交一次，全程未 push、未建远程仓库；`git log --oneline` 可查。
