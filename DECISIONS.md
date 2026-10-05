# DECISIONS.md

记录本项目中每一个"需要拍板"的决定和理由。按时间顺序追加。

## D1. 本机没有 Ollama，真实模型部分全部跳过（2026-10-05）

- 检查了 `which ollama`、`/usr/local/bin/ollama`、`/opt/homebrew/bin/ollama`、
  `/Applications/Ollama.app`，均不存在。
- 按规则"如果本机没装 Ollama，不要安装"，**不安装**，跳过范围里依赖真实模型的
  两件事：范围 1 的模型验证/下载、范围 9 的真实结果表。
- 代码仍然按"可插拔后端"写完：`OllamaBackend` 写好并做了可测的单元测试，
  一旦装上 Ollama 就能直接跑 `evals/record.py` 和
  `python -m evals.run_eval --backend ollama`。

## D2. 模型选择（未验证，只是配置默认值）

- 范围 1 要求优先用本机已下载的模型，但本机没有 Ollama，无法执行 `ollama list`。
- 于是把默认模型定为 `qwen2.5:7b`（`agent/config.py` 中），理由：
  1. 参数量 7.6B，满足"8B 以下"；
  2. 官方 README 明确支持 tool calling（模板里带 tools 支持）；
  3. Apache 2.0 许可；
  4. 中英双语，与本项目的使用场景（中文使用者、英文语料）匹配。
- 备选 `llama3.1:8b`（正好 8B，工具调用支持成熟），写成注释，方便换。
- **此选择未经过真实验证**，等装好 Ollama 后先 `ollama list` 看已有模型，
  有支持的就不下载新的。

## D3. CI 门禁 job 的数据来源：手写 fixture 录制（2026-10-05）

- 范围 7 要求"CI 上没有 Ollama，所以门禁 job 用录制好的模型响应来跑"。
- 本机没有 Ollama，**无法录制真实模型响应**。两个选项：
  1. 门禁 job 也跳过 → 范围 7 完不成；
  2. 用手写的 fixture 响应充当"录制"，如实标注。
- 选了 2。具体设计：
  - `evals/recordings/*.json`：每个 case 一份脚本化的模型回复序列
    （理想轨迹：该调工具的回合返回工具调用，最后回合返回最终答案）。
    由 `evals/make_recordings.py` 从 `cases.jsonl` 生成，人工可读、可改。
  - `evals/recording.py`：`RecordingBackend` 按回合回放这些响应，循环里
    工具是**真实执行**的，只是模型回复是脚本。
  - `evals/baseline.json`：`run_eval --backend recording` 的真实输出。
  - 门禁 `evals/gate.py` 只比较准确率指标，不比较延迟（不同机器延迟不可比，
    拿延迟做门禁会随机失败——这是单独一个决定，见 D4）。
- **这套数字的含义必须说清楚**：fixture 是"理想模型"的轨迹，所以基线指标是
  对评测管线本身的回归检测（循环、工具分发、打分、指标计算有没有被改坏），
  **不代表任何真实模型的能力**。装上 Ollama 后用 `evals/record.py` 重新录制，
  baseline 换成真实录制，门禁就升级为模型回归门禁——管线代码不用改。

## D4. 门禁不比较延迟，只比较三个准确率（2026-10-05）

- 延迟取决于跑评测的机器和当时的负载，GitHub Actions 的机器和本机毫无可比性，
  拿它当门禁只会产生随机失败。
- 所以 `gate.py` 只比较：tool_selection_accuracy、argument_accuracy、
  answer_accuracy 三个指标，任一低于基线就退出码 1。
- 延迟仍然照常统计并写进结果 JSON（P50/P95），只是不参与门禁。

## D5. 评测用例的语言用英文（2026-10-05）

- docs/ 里的 10 篇语料是英文（公开领域文本，见 D6），期望答案要用
  `contains`/`regex` 规则做机器判定，英文的子串匹配比中文分词更稳。
- 项目文档（README、STATUS、walkthrough）用中文，代码注释和评测数据用英文，
  这个组合最简单也最好解释。

## D6. docs/ 语料：公开领域的英文短文本，摘录并标注来源（2026-10-05）

- 10 篇全部选公有领域（public domain）文本：美国政府的文件天然无版权，
  19 世纪及更早的文学作品在 US 已进入公有领域（Project Gutenberg 提供）。
- 每篇只摘 1-2 段，来源和许可写进 `docs/SOURCES.md`，带原始 URL。
- 摘录是我从公开领域原文转录的短段落；SOURCES.md 里注明"为摘录版"，
  保证透明。

## D7. git 身份用仓库本地配置（2026-10-05）

- 本机没有配置 git user.name / user.email，全局配置我不能动（范围外）。
- 只在当前仓库设置 `user.name=yuhao`、`user.email=yuhao@local`，
  不影响其他仓库，也不影响 push（本项目本来就不 push）。

## D8. 工具错误不抛异常，返回 {"error": ...}（2026-10-05）

- 工具执行失败（比如计算器收到非法表达式）时，agent 循环把错误字符串
  作为工具结果返回给模型，让模型有机会纠正或换路子，而不是整个循环崩掉。
- 这也是小模型工具调用的常见模式：把失败当作观察结果反馈回去。
- 工具内部仍然抛 `ToolExecutionError`，由循环统一捕获打包，
  单元测试针对异常本身断言，语义更清楚。

## D9. Ollama 客户端用 httpx 同步调用，不用 SDK（2026-10-05）

- Ollama 没有官方 Python SDK，第三方 `ollama-python` 只是 httpx 的薄封装。
- 直接用 httpx POST `http://<host>/api/chat`（`stream=false`），
  依赖少、代码短、好解释，失败模式（连接拒绝）也好测。
- host 从环境变量 `OLLAMA_HOST` 读，默认 `http://localhost:11434`。

## D10. Ollama 装好后执行解锁步骤，D2 的默认模型被证实可用（2026-10-05 上午）

- 本机装好 Ollama 0.35.1，`ollama list` 确认 `qwen2.5:7b`（7.6B，Q4_K_M
  量化）已下载，与 D2 预先写的默认值一致，没有换模型。
- 按 STATUS.md 的解锁步骤执行：
  1. `python -m evals.record --model qwen2.5:7b` → 50/50 条全部录制成功，
     无一条以循环错误结束（退出码 0）；
  2. `python -m evals.run_eval --backend recording --out evals/baseline.json`
     → 用真实录制重建门禁基线。
- fixture 录制被真实录制覆盖；fixture 本身仍可随时用
  `python -m evals.make_recordings.py` 重新生成，旧版本也在 git 历史里。
- 门禁语义随之升级：从"管线回归检测"变成"真实模型回归门禁"——
  以后改 prompt、换模型、改工具，只要重录就能看出能力涨跌。

## D11. 共享本机 Ollama 的另一个进程导致首次录制几乎停滞（2026-10-05 上午）

- 第一次后台录制启动后发现机器上有**另一个项目**的评测进程同时对同一台
  Ollama 服务器发请求（最多 4 个并发连接），我的请求被排队，约 100 秒才
  完成一条，且 first case 迟迟无产出。
- 处理：
  1. 给 `agent/llm.py` 补了 `httpx.TimeoutException` 的翻译（此前只有
     ConnectError 被翻译，读超时会以裸异常打崩录制脚本）；
  2. 重跑时 `OLLAMA_TIMEOUT=900` + `python -u`（无缓冲，进度可见）；
  3. 只观察系统状态（lsof 端口占用），不读不改对方项目的任何文件。
- **对本报告数字的影响**：录制和 live 评测期间该进程仍在运行，
  延迟数字（P50/P95）是"共享服务器下的真实值"，会偏高且波动；
  三个准确率不受影响（推理结果与排队时间无关）。

## D12. 参数比较忽略格式空白；工具选择保持严格列表相等（2026-10-05 上午）

- 真实模型的 7/12 条 calculator 用例参数"失败"纯粹是 `744 / 8` vs
  `744/8` 的空格差异——语义完全相同。把这种算错是打分器的缺陷，
  会让 headline 数字（参数准确率 0.425 → 0.575）严重失真。
- 修法：`evals/scoring.py::_canonical` 在大小写归一化之外去掉**全部**
  空白。词的选择和顺序仍然敏感，所以 15 条 search 的查询改写照样失败，
  没有用宽松度掩盖真实错误。
- 反向决定：**工具选择**保持严格列表相等（`sorted(expected) ==
  sorted(used)`），模型对同一工具的**重复调用算失败**（真实案例
  calc-004：同一轮连调两次 calculator）。理由：重复调用是真实的延迟
  浪费和混乱信号，回归门禁应该暴露它；此前文档里"集合相等"的说法与
  代码不符，已把文档改成与代码一致的"列表严格相等"。
