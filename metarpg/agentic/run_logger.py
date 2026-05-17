"""Run logger for agentic pipeline.

Emits:
- events.jsonl   — chronological machine-readable event stream
- errors.jsonl   — exception records
- run_manifest.json — run-level metadata
- summary.md     — human-readable run summary
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunLogger:
    run_id: str
    run_dir: Path
    _events_fh: Any = field(init=False)
    _errors_fh: Any = field(init=False)

    def __post_init__(self) -> None:
        self._events_fh = open(self.run_dir / "events.jsonl", "w", encoding="utf-8")
        self._errors_fh = open(self.run_dir / "errors.jsonl", "w", encoding="utf-8")
        self._emit("run_start", 0, "run", "Run started")

    def _emit(self, event: str, turn: int, stage: str, message: str = "") -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "run_id": self.run_id,
            "turn": turn,
            "stage": stage,
            "event": event,
            "message": message,
        }
        self._events_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._events_fh.flush()

    def emit(self, turn: int, stage: str, event: str, message: str = "") -> None:
        self._emit(event, turn, stage, message)

    def log_error(
        self,
        turn: int,
        stage: str,
        error_type: str,
        error_message: str,
        traceback_str: str = "",
        artifact: str = "",
    ) -> None:
        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "run_id": self.run_id,
            "turn": turn,
            "stage": stage,
            "error_type": error_type,
            "error_message": error_message,
        }
        if traceback_str:
            record["traceback"] = traceback_str
        if artifact:
            record["artifact"] = artifact
        self._errors_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._errors_fh.flush()
        self._emit("error", turn, stage, f"{error_type}: {error_message}")

    def close(
        self,
        turns_attempted: int,
        turns_completed: int,
        scorecards: list[dict[str, Any]],
        hard_failures: list[str],
        medium_issues: list[str],
        soft_issues: list[str],
        case_id: str = "greyfen_interactive",
        models: dict[str, str] | None = None,
    ) -> None:
        self._emit("run_end", turns_attempted, "run", f"Completed {turns_completed}/{turns_attempted} turns")
        self._events_fh.close()
        self._errors_fh.close()

        if models is None:
            models = {
                "writer": "deepseek-flash",
                "translator": "qwen3.6-local",
                "soft_auditor": "qwen3.6-local",
                "editor": "qwen3.6-local",
            }

        manifest = {
            "run_id": self.run_id,
            "case_id": case_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "mode": "live",
            "models": models,
            "turns_expected": turns_attempted,
            "turns_written": turns_completed,
            "missing_turns": [],
            "hard_failures": hard_failures,
            "medium_issues": medium_issues,
            "soft_issues": soft_issues,
            "acceptable": len(hard_failures) == 0,
        }
        with open(self.run_dir / "run_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        lines = [
            f"# Run {self.run_id}",
            "",
            f"Case: {case_id}",
            f"Turns attempted: {turns_attempted}",
            f"Turns completed: {turns_completed}",
        ]
        if hard_failures:
            lines.extend(["", "## Failures"])
            for hf in hard_failures:
                lines.append(f"- {hf}")
        lines.extend(["", "## Scores"])
        for i, sc in enumerate(scorecards, 1):
            lines.append(
                f"- turn_{i:03d}: experience {sc.get('player_experience_score', 0):.2f} / grounding {sc.get('grounding_score', 0):.2f}"
            )
        with open(self.run_dir / "summary.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
