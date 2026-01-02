from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path
    sandbox_root: Path

    @staticmethod
    def from_env() -> "AppConfig":
        repo_root = Path(__file__).resolve().parents[3]
        sandbox_root = repo_root / ".sentinel" / "sandboxes"
        return AppConfig(repo_root=repo_root, sandbox_root=sandbox_root)


DEFAULT_CONFIG = AppConfig.from_env()
