from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any

from agents import ApplyPatchTool, apply_diff
from agents.editor import ApplyPatchOperation, ApplyPatchResult


def _parse_unified_diff(diff: str) -> list[dict[str, Any]]:
    """Parse a unified diff into structured line objects."""
    lines = []
    for line in diff.split("\n"):
        if not line:
            continue
        if line.startswith("@@"):
            # Hunk header - skip or mark as context
            lines.append({"type": "hunk", "content": line})
        elif line.startswith("+++") or line.startswith("---"):
            # File headers - skip
            continue
        elif line.startswith("+"):
            lines.append({"type": "add", "content": line[1:]})
        elif line.startswith("-"):
            lines.append({"type": "remove", "content": line[1:]})
        else:
            # Context line (starts with space or no prefix)
            content = line[1:] if line.startswith(" ") else line
            lines.append({"type": "context", "content": content})
    return lines


def _make_structured_result(
    operation_type: str,
    file_path: str,
    diff: str,
    old_content: str = "",
    new_content: str = "",
) -> ApplyPatchResult:
    """Create an ApplyPatchResult with structured diff data for the frontend."""
    action_word = {"create_file": "Created", "update_file": "Updated", "delete_file": "Deleted"}.get(
        operation_type, "Modified"
    )

    structured_output = {
        "message": f"{action_word} {file_path}",
        "operation_type": operation_type,
        "file_path": file_path,
        "diff_lines": _parse_unified_diff(diff),
        "old_content": old_content,
        "new_content": new_content,
    }

    return ApplyPatchResult(output=json.dumps(structured_output))


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
        return _make_structured_result(
            operation_type="create_file",
            file_path=operation.path,
            diff=diff,
            old_content="",
            new_content=content,
        )

    async def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        target = self._resolve(operation.path)
        original = target.read_text(encoding="utf-8")
        diff = operation.diff or ""
        patched = apply_diff(original, diff)
        target.write_text(patched, encoding="utf-8")
        self._applied.add(self._fingerprint(operation))
        return _make_structured_result(
            operation_type="update_file",
            file_path=operation.path,
            diff=diff,
            old_content=original,
            new_content=patched,
        )

    async def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        target = self._resolve(operation.path)
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        target.unlink(missing_ok=True)
        self._applied.add(self._fingerprint(operation))
        return _make_structured_result(
            operation_type="delete_file",
            file_path=operation.path,
            diff=operation.diff or "",
            old_content=original,
            new_content="",
        )

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
