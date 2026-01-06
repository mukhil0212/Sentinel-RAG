from __future__ import annotations

from pathlib import Path
import hashlib

from agents import ApplyPatchTool, apply_diff
from agents.editor import ApplyPatchOperation, ApplyPatchResult


class WorkspaceEditor:
    """Apply apply_patch operations inside a sandbox workspace."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._applied: set[str] = set()

    async def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        target = self._resolve(operation.path, ensure_parent=True)
        diff = operation.diff or ""
        try:
            content = apply_diff("", diff, create=True)
        except TypeError:
            content = apply_diff("", diff, mode="create")
        target.write_text(content, encoding="utf-8")
        self._applied.add(self._fingerprint(operation))
        return ApplyPatchResult(output=f"Created {operation.path}")

    async def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        target = self._resolve(operation.path)
        original = target.read_text(encoding="utf-8")
        diff = operation.diff or ""
        patched = apply_diff(original, diff)
        target.write_text(patched, encoding="utf-8")
        self._applied.add(self._fingerprint(operation))
        return ApplyPatchResult(output=f"Updated {operation.path}")

    async def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        target = self._resolve(operation.path)
        target.unlink(missing_ok=True)
        self._applied.add(self._fingerprint(operation))
        return ApplyPatchResult(output=f"Deleted {operation.path}")

    def _resolve(self, relative: str, ensure_parent: bool = False) -> Path:
        candidate = Path(relative)
        target = candidate if candidate.is_absolute() else (self._root / candidate)
        target = target.resolve()
        try:
            target.relative_to(self._root)
        except ValueError:
            raise RuntimeError(f"Operation outside workspace: {relative}") from None
        if ensure_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _fingerprint(self, operation: ApplyPatchOperation) -> str:
        hasher = hashlib.sha256()
        hasher.update(operation.type.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(operation.path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update((operation.diff or "").encode("utf-8"))
        return hasher.hexdigest()


def make_apply_patch_tool(root: Path) -> ApplyPatchTool:
    """Create an apply_patch tool bound to a sandbox workspace."""
    editor = WorkspaceEditor(root)
    return ApplyPatchTool(editor=editor)
