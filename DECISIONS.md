# DECISIONS.md

Every decision in this project that required a call, and why. Appended in
chronological order.

## D1. No Ollama on this machine — all real-model work initially skipped (2026-10-05)

- Checked `which ollama`, `/usr/local/bin/ollama`, `/opt/homebrew/bin/ollama`,
  `/Applications/Ollama.app` — none existed.
- Per the rule "if Ollama is not installed locally, do not install it": **no
  install**, and the two real-model deliverables were skipped — model
  validation/download (scope 1) and the real results table (scope 9).
- The code was still written with pluggable backends: `OllamaBackend` was
  implemented with unit tests, ready to run `evals/record.py` and
  `python -m evals.run_eval --backend ollama` the moment Ollama appeared.

## D2. Model choice (unverified at the time; a config default only)

- Scope 1 said to prefer an already-downloaded local model, but with no
  Ollama there was no `ollama list` to run.
- The default model was set to `qwen2.5:7b` (in `agent/config.py`), because:
  1. 7.6B parameters, satisfies "under 8B";
  2. the official README documents tool calling (tools support in the chat
     template);
  3. Apache 2.0 license;
  4. bilingual (Chinese/English), matching this project's usage (Chinese
     speaker, English corpus).
- The alternative `llama3.1:8b` (exactly 8B, mature tool-calling support) is
  kept as a comment for easy switching.
- **This choice was unverified at the time**; the plan was to run
  `ollama list` once Ollama was installed and reuse an existing model if one
  fit.

## D3. CI gate data source: hand-written fixture recordings (2026-10-05)

- Scope 7 required "CI has no Ollama, so the gate job runs on recorded model
  responses".
- With no Ollama locally, **real recordings were impossible**. Two options:
  1. skip the gate job too → scope 7 undeliverable;
  2. use hand-written fixture responses standing in for recordings, labeled
     honestly.
- Option 2 was chosen. The design:
  - `evals/recordings/*.json`: one scripted model-response sequence per case
    (ideal trajectory: the tool call returns in the turn that needs it, the
    final turn returns the final answer). Generated from `cases.jsonl` by
    `evals/make_recordings.py`, human-readable and editable.
  - `evals/recording.py`: `RecordingBackend` replays these responses
    turn by turn; the tools are **executed for real** — only the model
    responses are scripted.
  - `evals/baseline.json`: the real output of `run_eval --backend recording`.
  - The gate `evals/gate.py` compares accuracy metrics only, never latency
    (a separate decision, D4).
- **What these numbers mean must be crystal clear**: fixtures are an "ideal
  model" trajectory, so the baseline is a regression check on the eval
  pipeline itself (loop, tool dispatch, scoring, metrics) and **represents no
  real model's capability**. Once Ollama existed, `evals/record.py` re-recorded
  everything and the baseline became real, upgrading the gate to a model
  regression gate — no pipeline code changed.

## D4. The gate never compares latency, only the three accuracies (2026-10-05)

- Latency depends on the machine and its load; a GitHub Actions runner and a
  laptop are not comparable, so gating on latency would fail randomly.
- `gate.py` therefore compares only tool_selection_accuracy,
  argument_accuracy, and answer_accuracy; any value below baseline exits 1.
- Latency is still measured and written to the results JSON (P50/P95); it
  just never gates.

## D5. Eval cases are in English (2026-10-05)

- The corpus in `docs/` is English (public-domain texts, see D6), and
  expected answers are judged by machine `contains`/`regex` rules — English
  substring matching is far more robust than Chinese word segmentation.
- Project docs in Chinese (README, STATUS, walkthrough) with English code
  comments and eval data was the simplest, most explainable combination
  (later revised when the repo was prepared for publication — the public
  docs are now English).

## D6. The `docs/` corpus: public-domain English excerpts with provenance (2026-10-05)

- All texts are public domain: US government documents are copyright-free by
  nature, and 19th-century-and-earlier literature is out of copyright in the
  US (available via Project Gutenberg).
- Each file is a 1–2 paragraph excerpt; provenance and license are recorded
  in `docs/SOURCES.md` with the original URLs.
- The excerpts were transcribed from public-domain sources; SOURCES.md notes
  they are excerpts, for transparency.

## D7. Repo-local git identity (2026-10-05)

- The machine had no git user.name / user.email configured, and the global
  config was out of scope.
- Only this repository sets `user.name=yuhao`, `user.email=yuhao@local` —
  no effect on other repos or on pushing.

## D8. Tool errors return `{"error": ...}` instead of raising (2026-10-05)

- When a tool fails (e.g. the calculator gets an invalid expression), the
  agent loop feeds the error string back to the model as the tool result,
  giving the model a chance to correct course instead of crashing the loop.
- This is a common pattern for small-model tool calling: treat failures as
  observations.
- Tools still raise `ToolExecutionError` internally; the loop catches and
  packages it, and unit tests assert on the exception itself, which keeps
  the semantics clean.

## D9. Ollama client: synchronous httpx, no SDK (2026-10-05)

- Ollama has no official Python SDK, and the third-party `ollama-python` is
  a thin httpx wrapper anyway.
- POSTing `http://<host>/api/chat` (`stream=false`) directly with httpx means
  fewer dependencies, less code, easier explanation, and an easily testable
  failure mode (connection refused).
- The host comes from `OLLAMA_HOST`, defaulting to `http://localhost:11434`.

## D10. Ollama installed — unlock steps executed, D2's default model confirmed (2026-10-05, morning)

- Ollama 0.35.1 installed; `ollama list` confirmed `qwen2.5:7b` (7.6B, Q4_K_M
  quantization) already downloaded — exactly D2's pre-written default, no
  model change.
- Executed the unlock steps from STATUS.md:
  1. `python -m evals.record --model qwen2.5:7b` → 50/50 cases recorded, none
     ending in a loop error (exit code 0);
  2. `python -m evals.run_eval --backend recording --out evals/baseline.json`
     → the gate baseline rebuilt from real recordings.
- Fixture recordings were overwritten with real ones; fixtures can still be
  regenerated anytime with `python -m evals.make_recordings.py`, and the old
  version remains in git history.
- The gate's semantics upgraded accordingly: from "pipeline regression check"
  to "real-model regression gate" — change a prompt, model, or tool, re-record,
  and the gate shows the capability delta.

## D11. Another process sharing the local Ollama server nearly stalled the first recording (2026-10-05, morning)

- Shortly after the first background recording started, an eval process from
  **another project** was observed hitting the same Ollama server (up to 4
  concurrent connections); my requests queued to ~100 s per case and the
  first case produced nothing for a long time.
- Handling:
  1. added translation for `httpx.TimeoutException` in `agent/llm.py`
     (previously only ConnectError was translated; a read timeout would crash
     the recording script with a bare exception);
  2. re-ran with `OLLAMA_TIMEOUT=900` + `python -u` (unbuffered, progress
     visible);
  3. only observed system state (lsof on the port); never read or modified
     the other project's files.
- **Effect on the numbers**: that process was still running during the
  recording and the first live eval, so latency (P50/P95) from those runs is
  "real value under a shared server" — inflated and noisy. The three
  accuracies are unaffected (inference results are independent of queueing).

## D12. Argument comparison ignores formatting whitespace; tool selection stays strict list equality (2026-10-05, morning)

- In the real model's first recording run, 7 of 12 calculator cases "failed"
  purely on whitespace (`744 / 8` vs `744/8`) — semantically identical.
  Scoring those as failures is a scorer defect that badly distorts the
  headline number (argument accuracy 0.425 → 0.575 after the fix).
- Fix: `evals/scoring.py::_canonical` strips **all** whitespace in addition
  to case normalization. Word choice and order remain sensitive, so the 15
  search queries that get rephrased still fail — no real error is masked by
  leniency.
- The opposite call: **tool selection** keeps strict list equality
  (`sorted(expected) == sorted(used)`), and **duplicate calls of the same
  tool count as failure** (real case calc-004: calculator called twice in one
  turn). Rationale: duplicate calls are real wasted latency and a confusion
  signal the gate should expose. Earlier docs said "set equality", which did
  not match the code; the docs were corrected to the code's "strict list
  equality".

## D13. results_live.json committed; README/STATUS use the clean idle-server rerun (2026-10-05, midday)

- The first live eval (17:28Z) suffered contention from that other process:
  two environment failures and a P50 inflated ~2×. After it ended, `/api/ps`
  was verified empty with no other connections, and the eval was re-run into
  `evals/results_live.json` (18:29Z) with zero environment failures.
- The results file is **committed to git**: every number in the README
  results tables must be traceable to script output on disk — this file is
  that evidence. `evals/results.json` remains a local throwaway and
  gitignored (the gate generates it fresh in CI).
- README/STATUS live numbers all switched to the clean run:
  0.940 / 0.550 / 0.820, P50 5,975 ms / P95 16,536 ms.
- Argument accuracy is broken out per tool (search 0/15, calculator 10/12,
  workdays 12/13), with the reason search is 0/15 stated: the scorer requires
  the query verbatim (same words, same order even after case/whitespace
  normalization), and the model rephrases every time.
