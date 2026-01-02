from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sandbox:
    id: str
    root: Path


def create_sandbox(repo_root: Path, sandbox_root: Path) -> Sandbox:
    # Copy the repo into a fresh, isolated workspace for safe patching/validation.
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox_id = uuid.uuid4().hex
    sandbox_path = sandbox_root / sandbox_id

    shutil.copytree(
        repo_root,
        sandbox_path,
        dirs_exist_ok=False,
        # Skip large/unsafe directories to keep the sandbox lightweight.
        ignore=shutil.ignore_patterns(".git", ".sentinel", ".venv", "node_modules"),
    )

    return Sandbox(id=sandbox_id, root=sandbox_path)
