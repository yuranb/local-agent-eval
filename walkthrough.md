# walkthrough.md — 项目走读（按数据流顺序）

目的：明天早上凭这一份文档把这个项目从头到尾讲清楚。
读法：按下面顺序打开文件，每节标注了关键行号。

---

## 第 0 站：语料 `docs/`

11 篇公有领域英文短文（林肯葛底斯堡演说、独立宣言摘录、莎士比亚十四行诗
18、伊索寓言两篇、孙子兵法 Giles 译本、物种起源结尾、大宪章、Invictus、
Frost 诗意路、爱丽丝开头）。每篇 1–4 段，是检索工具的测试语料。
`docs/SOURCES.md` 是来源和许可清单（检索工具**不索引**它，只索引 `*.txt`）。

## 第 1 站：三个工具 `agent/tools.py`

每个工具 = 一个普通 Python 函数 + 一份 JSON schema（给模型看的"说明书"）
+ 统一的分发入口。

- **search_docs**（第 26 行）：把 `docs/*.txt` 逐行读，查询按空格拆词，
  一行得几分 = 包含几个查询词（大小写不敏感），第 46 行是打分那一句。
  按分数、文件名、行号排序，取前 top_k。没有向量库没有嵌入——
  面试时可以主动说"这是故意的词面匹配，够用且零依赖，升级路径是 BM25/向量"。
- **calculator**（第 113 行）：核心在第 98 行 `_eval_node`，用 Python 的
  `ast` 模块把表达式解析成语法树，只放行数字和 `+ - * / // % **`、括号、
  一元正负号（第 103 行的白名单分发）。任何名字、函数调用、属性访问直接
  拒绝——所以 `__import__('os')` 这类注入根本到不了执行那一步
  （tests/test_tools.py 里有 7 个安全相关用例）。
- **add_workdays**（第 159 行）：从起始日期逐天走，第 182 行
  `weekday() < 5` 跳过周六周日，支持负数（往前）和 0。
- **execute_tool**（第 236 行）：分发 + 兜底。未知工具、参数错、执行失败
  全部变成 `{"error": "..."}` 返回给模型（DECISIONS.md D8），不抛异常。

## 第 2 站：Ollama 客户端 `agent/llm.py`

- `OllamaBackend.chat`（第 54 行）：一个 httpx POST 打到
  `http://localhost:11434/api/chat`，`stream=false`，带 tools schema
  （第 58 行）。连接失败翻译成人话（第 63 行，本机实测就是这个报错文案）。
- `normalize_message`（第 17 行）：把不同版本 Ollama 返回的 tool_calls
  归一化——有的版本 `arguments` 是 JSON 字符串，有的是对象（第 31 行处理），
  统一成 `{"function": {"name": ..., "arguments": dict}}`。
  这个函数是纯函数，所以没装 Ollama 也能单测（tests/test_llm.py 9 个用例）。

## 第 3 站：agent 循环 `agent/loop.py`（全项目核心，50 行）

`run_agent`（第 28 行）：

1. 消息序列 = system 提示 + user 问题。
2. 循环最多 `MAX_STEPS=5` 轮（`agent/config.py:17`，防失控）：
   - 第 49 行：调 `backend.chat(messages, tools)` 拿一条助手消息；
   - 第 53 行：没有 `tool_calls` → 这就是最终答案，返回；
   - 有 → 真实执行每个工具，结果 JSON 序列化后以 `role:"tool"` 消息
     追加进对话（第 66 行），继续下一轮。
3. 跑满 5 轮还没答案 → 返回带 `error` 的结果（第 72 行）。

关键抽象：`backend` 只要求有 `chat(messages, tools)` 方法。真实 Ollama、
录制回放、测试 stub 三种实现共用这一个循环——这就是 CI 没有 Ollama 也能
跑门禁的原因。

## 第 4 站：API `server/app.py`

- `create_app(backend=None)`（第 44 行）：工厂函数。传了 backend（测试）
  就用注入的；没传就在第一个请求时惰性创建 `OllamaBackend`（第 50 行），
  所以 import 这个模块永远不会因为没装 Ollama 而挂。
- `POST /chat`（第 62 行）：跑完整循环，返回
  `{answer, tool_calls:[{tool, arguments, result}], steps, error, latency_ms}`。
  延迟是 `perf_counter` 实测（第 81 行）。请求体校验：question 非空
  （第 24 行），空则 422。

## 第 5 站：评估集 `evals/cases.jsonl`

50 条 JSONL：15 search / 12 calculator / 13 workday / 10 no_tool。
每条五个关键字段：`question`、`expected_tools`、`expected_args`
（按工具名分组）、`answer_rule`（contains 或 regex）。
`tests/test_eval_dataset.py` 做两层校验：结构（数量、字段、schema 匹配）
和**一致性**——每条用例的期望参数拿去真跑工具、答案规则去匹配真实工具
输出（第 105 行附近）。search-003 就是被这个测试抓出来修好的。

## 第 6 站：打分 `evals/scoring.py`（纯函数，无模型）

- `tool_selection_ok`（第 32 行）：调用的工具集合 == 期望集合（排序后比较）。
- `arguments_ok`（第 37 行）：期望参数是某次实际调用的**子集**即可；
  第 15 行 `_canonical` 做归一化——数字 "3" 和 3 相等、大小写和空白不敏感。
- `answer_ok`（第 56 行）：contains（归一化子串）或 regex。
- `percentile`（第 66 行）：线性插值法（numpy 默认约定），第 74 行算秩。
- `score_case` / `compute_metrics`（第 81/106 行）：聚合出三个准确率；
  argument_accuracy 的分母**只算有期望参数的用例**（40 条），no_tool 用例
  不进分母。

## 第 7 站：评估入口 `evals/run_eval.py`

`main` 按参数选后端：`recording`（回放，第 78 行）或 `ollama`（真实）。
每个用例：新建后端 → 计时跑 `run_agent` → `score_case`。后端崩溃也记为
失败用例而不是整个评测崩掉（第 53 行）。输出 JSON：全局 metrics +
每用例明细。**工具在 recording 模式下是真实执行的，只有模型回复是脚本。**

## 第 8 站：录制与门禁

- `evals/recording.py`：`RecordingBackend`（第 24 行）按轮次吐出录制的
  助手消息，吐完再要就报错（第 33 行的 chat）。
- `evals/make_recordings.py`：从 cases.jsonl 生成 fixture（理想轨迹）。
  `fixture_answer`（第 36 行）的答案文本来自**真实工具输出**，并自检必须
  满足该用例的 answer_rule 才允许写出（`build_turns`，第 71 行）。
  这些文件 `source: fixture`，含义见 DECISIONS.md D3。
- `evals/record.py`：在装了 Ollama 的机器上跑同一条循环、把每轮真实模型
  回复录下来，替换 fixture 后门禁就升级成真实模型门禁。**本机未执行过。**
- `evals/gate.py`：`compare`（第 24 行）只比较三个准确率，第 35 行是
  判定 + 容差（1e-9，防浮点噪声）。低于基线退出码 1，输入坏了退出码 2，
  通过 0。不比较延迟（DECISIONS.md D4）。
- `evals/baseline.json`：上面这条 recording 流水线的真实输出，进 git，
  是门禁的比较基准。

## 第 9 站：CI 与容器

- `.github/workflows/ci.yml`：两个 job。`test` 跑 pytest；
  `eval-gate` 依赖 test 通过后，跑 recording 评估再跑 gate。
  CI 上没有 Ollama，所以用录制回放——这就是第 7、8 站设计的意义。
  （未在真实 GitHub 上执行过：规则禁止 push。）
- `Dockerfile`：python:3.12-slim，装依赖、拷代码、uvicorn 起服务。
  容器里没有 Ollama，`OLLAMA_HOST` 默认指向 host.docker.internal。
  **未验证**（本机无 Docker）。

## 测试地图（106 个）

| 文件 | 数量 | 测什么 |
|---|---|---|
| tests/test_tools.py | 37 | 三个工具，含安全注入、除零、跨周末 |
| tests/test_scoring.py | 19 | 打分纯函数、百分位、分母正确性 |
| tests/test_eval_pipeline.py | 16 | fixture 生成、回放、端到端评估、门禁退出码 |
| tests/test_eval_dataset.py | 10 | 数据集结构与"用例↔工具输出"一致性 |
| tests/test_llm.py | 9 | 消息归一化、连接错误翻译 |
| tests/test_loop.py | 8 | 循环：直接答、工具回传、失败恢复、步数上限 |
| tests/test_app.py | 7 | API：trace 结构、校验、错误字段 |

---

## 面试官最可能问的 8 个问题

**Q1. "你的 agent 循环怎么防止模型无限调工具？"**
`agent/loop.py:49`（for step in range(1, max_steps+1)）和
`agent/loop.py:72`（超限返回 error）。步数上限 5 在 `agent/config.py:17`，
环境变量可调。补充：每轮工具结果是 append 进消息序列的
（`agent/loop.py:66`），模型看得到历史，不会重复同一次调用。

**Q2. "工具是小模型调的，参数错了怎么办？"**
三层防线：(a) 消息归一化兜住 Ollama 版本差异 `agent/llm.py:31`；
(b) `agent/tools.py:236` execute_tool 把一切失败变成 `{"error":...}`
回传模型让它自己纠正（tests/test_loop.py 的
test_loop_survives_tool_failure_and_reports_it_to_model 验证了模型确实
能看到错误文本）；(c) 打分时参数匹配做了数字/字符串归一化
`evals/scoring.py:15`，模型发 `"3"` 和 3 都算对。

**Q3. "calculator 直接 eval 用户输入不是不安全吗？"**
不用 eval。`agent/tools.py:98` 的 `_eval_node` 只走 ast 白名单：数字、
二元运算、一元符号，其余节点（名字、调用、属性）在执行前就拒绝
（`agent/tools.py:103` 附近）。tests/test_tools.py 的
test_calculator_rejects_non_arithmetic_input 列了 7 种注入尝试。

**Q4. "CI 上没有 Ollama，评估门禁怎么跑？"**
后端可插拔：循环只依赖 `chat()` 接口（`agent/loop.py:28`），CI 用
`RecordingBackend` 回放录制（`evals/recording.py:24`），工具照常真实执行。
当前录制是 fixture（理想轨迹），所以基线 1.000 验证的是管线而非模型——
这个区别我在 README 里写明了，升级路径是 `evals/record.py` 在有 Ollama
的机器重录。设计理由在 DECISIONS.md D3。

**Q5. "为什么门禁不比较延迟？"**
`evals/gate.py:24` 的 compare 只挑三个准确率指标。延迟依赖跑评测的机器
（CI 的 ubuntu runner 和我的笔记本毫无可比性），拿它当门禁会产生随机
失败。延迟照样统计进结果 JSON（`evals/scoring.py:66` 百分位实现），
只是不 gate。DECISIONS.md D4。

**Q6. "argument accuracy 的分母是什么？为什么这么定？"**
`evals/scoring.py:106` compute_metrics：分母只算 `arguments_evaluated`
为真的用例（`evals/scoring.py:81` score_case 里由 expected_args 非空
决定）。10 条 no_tool 用例没有参数可言，进分母只会稀释指标。
`tests/test_scoring.py::test_compute_metrics_aggregates_and_uses_correct_denominators`
专门锁这个行为。

**Q7. "百分位是怎么算的？"**
`evals/scoring.py:66` percentile，线性插值法（和 numpy 默认一致）：
rank = (n-1)*p/100（第 74 行），在相邻两个序值之间按小数部分插值。
奇数个值的 P50 就是中位数；tests/test_scoring.py 里有单值、奇数、
插值、空列表四个用例。

**Q8. "50 条用例哪来的，怎么保证不是拍脑袋写的？"**
AI 起草 + 机器一致性测试兜底 + 人工审核（README 里如实写了"尚未人工
复核"）。关键是 `tests/test_eval_dataset.py`：每条 search 用例的期望
查询真去跑 search_docs、每条 calculator/workday 用例的期望参数真去跑
工具，答案规则必须能匹配真实输出，否则测试红。search-003 就是这么
修出来的——原查询词命中的行和答案所在行因折行不是同一行。

---

## 一句话总结每个文件

- `docs/`：公有领域语料（11 篇）+ 来源清单
- `agent/tools.py`：三个工具 + schema + 安全分发
- `agent/llm.py`：Ollama HTTP 客户端 + 消息归一化
- `agent/loop.py`：模型↔工具循环（可插拔后端，全项目心脏）
- `agent/config.py`：模型名 / host / max_steps，环境变量可覆盖
- `server/app.py`：FastAPI /chat，惰性后端 + 注入
- `evals/cases.jsonl`：50 条用例（四类）
- `evals/scoring.py`：纯打分（集合匹配/参数子集/答案规则/百分位）
- `evals/run_eval.py`：评估入口，recording 和 ollama 双后端
- `evals/recording.py` / `make_recordings.py` / `record.py`：
  回放 / 生成 fixture / 真实录制（未执行）
- `evals/gate.py` + `baseline.json`：门禁 + 基线
- `.github/workflows/ci.yml`：pytest + 门禁两个 job（未实跑）
- `Dockerfile`：API 容器（未验证）
- `tests/`：106 个测试，全部通过
