"""Replay recorded model responses instead of calling a real model.

Each case has a JSON file in the recordings dir:
    {"case_id": "...", "source": "fixture" or "ollama:<model>", "turns": [...]}
`turns` is the exact list of assistant messages the model would return, in
order, one per loop step. Tools are still executed for real inside the loop —
only the model's side is scripted (DECISIONS.md D3).
"""
from __future__ import annotations

import json
from pathlib import Path


def load_recordings(recordings_dir: Path) -> dict:
    """Return {case_id: {"source": ..., "turns": [...]}} from a directory."""
    recordings = {}
    for path in sorted(Path(recordings_dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        recordings[data["case_id"]] = data
    return recordings


class RecordingBackend:
    """Backend that replays one case's scripted turns, one per chat() call."""

    def __init__(self, case_id: str, turns: list, source: str = "fixture"):
        self.case_id = case_id
        self.turns = list(turns)
        self.source = source
        self._index = 0

    def chat(self, messages, tools=None):
        if self._index >= len(self.turns):
            raise RuntimeError(
                f"recording for {self.case_id} exhausted at turn {self._index + 1} "
                f"(the agent loop wanted another model response)"
            )
        turn = self.turns[self._index]
        self._index += 1
        return turn
