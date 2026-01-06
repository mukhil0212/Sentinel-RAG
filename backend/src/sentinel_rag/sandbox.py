from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sandbox:
    id: str
    root: Path


def create_sandbox(sandbox_root: Path) -> Sandbox:
    """Create an empty per-session sandbox directory.

    This sandbox is intended to hold user-provided IaC files (Terraform/YAML/etc)
    for scanning and patching. It should not copy the application codebase.
    """
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox_id = uuid.uuid4().hex
    sandbox_path = sandbox_root / sandbox_id
    sandbox_path.mkdir(parents=False, exist_ok=False)

    return Sandbox(id=sandbox_id, root=sandbox_path)
