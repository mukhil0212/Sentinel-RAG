from __future__ import annotations

from pathlib import Path
import os

import hashlib

from agents import ApplyPatchTool, apply_diff
from agents.editor import ApplyPatchOperation, ApplyPatchResult


class WorkspaceEditor:
    """Apply apply_patch operations inside a sandbox workspace."""

    def __init__(self, root: Path, auto_approve: bool) -> None:
        self._root = root.resolve()
        self._auto_approve = auto_approve or os.environ.get("APPLY_PATCH_AUTO_APPROVE") == "1"
        self._approved: set[str] = set()

    async def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        # apply_diff turns a unified diff into file content (create mode).
        self._require_approval(operation)
        target = self._resolve(operation.path, ensure_parent=True)
        diff = operation.diff or ""
        try:
            content = apply_diff("", diff, create=True)
        except TypeError:
            content = apply_diff("", diff, mode="create")
        target.write_text(content, encoding="utf-8")
        return ApplyPatchResult(output=f"Created {operation.path}")

    async def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        # apply_diff transforms current content into patched content.
        self._require_approval(operation)
        target = self._resolve(operation.path)
        original = target.read_text(encoding="utf-8")
        diff = operation.diff or ""
        patched = apply_diff(original, diff)
        target.write_text(patched, encoding="utf-8")
        return ApplyPatchResult(output=f"Updated {operation.path}")

    async def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        self._require_approval(operation)
        target = self._resolve(operation.path)
        target.unlink(missing_ok=True)
        return ApplyPatchResult(output=f"Deleted {operation.path}")

    def _resolve(self, relative: str, ensure_parent: bool = False) -> Path:
        # Enforce that all edits stay inside the sandbox root.
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

    def _require_approval(self, operation: ApplyPatchOperation) -> None:
        # De-duplicate prompts for identical operations.
        fingerprint = self._fingerprint(operation)
        if self._auto_approve or fingerprint in self._approved:
            self._approved.add(fingerprint)
            return

        print("\n[apply_patch] approval required")
        print(f"- type: {operation.type}")
        print(f"- path: {operation.path}")
        if operation.diff:
            preview = operation.diff if len(operation.diff) < 400 else f"{operation.diff[:400]}…"
            print("- diff preview:\n", preview)
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            raise RuntimeError("Apply patch operation rejected by user.")
        self._approved.add(fingerprint)


def make_apply_patch_tool(root: Path, auto_approve: bool = True) -> ApplyPatchTool:
    editor = WorkspaceEditor(root, auto_approve)
    return ApplyPatchTool(editor=editor)
