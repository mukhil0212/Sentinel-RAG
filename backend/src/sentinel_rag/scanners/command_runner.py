from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str


def run_command(command: list[str], cwd: Path, timeout_s: int = 120) -> CommandResult:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
        return CommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=127,
            stdout="",
            stderr=str(exc),
        )
