from __future__ import annotations

import json
from pathlib import Path

from agents import function_tool


def make_read_file_tool(root: Path):
    root = root.resolve()

    @function_tool
    def read_file(path: str) -> str:
        """Read a UTF-8 text file from the sandbox.

        Args:
            path: Path to a file, relative to the sandbox root.
        """
        candidate = (root / path).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Path escapes sandbox root")
        if not candidate.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return candidate.read_text(encoding="utf-8")

    return read_file


def make_list_files_tool(root: Path):
    root = root.resolve()

    @function_tool
    def list_files(path: str | None = None, max_depth: int = 6) -> str:
        """List files in the sandbox (recursive).

        Args:
            path: Optional directory to list, relative to the sandbox root.
                  If omitted, lists from the sandbox root.
            max_depth: Maximum directory depth to traverse (guards against huge trees).

        Returns:
            JSON string with `base`, `files`, and `dirs` (relative paths).
        """
        base = root
        if path:
            base = (root / path).resolve()
            if root not in base.parents and base != root:
                raise ValueError("Path escapes sandbox root")
            if not base.exists():
                raise FileNotFoundError(f"Path not found: {path}")

        def depth(rel: Path) -> int:
            return 0 if str(rel) in (".", "") else len(rel.parts)

        files: list[str] = []
        dirs: list[str] = []

        for entry in base.rglob("*"):
            rel = entry.relative_to(base)
            if depth(rel) > max_depth:
                continue
            # Hide common noisy dirs
            if any(part in {".terraform", "node_modules", "__pycache__", ".venv", ".git"} for part in rel.parts):
                continue

            rel_str = rel.as_posix()
            if entry.is_dir():
                dirs.append(rel_str)
            elif entry.is_file():
                files.append(rel_str)

        payload = {
            "base": (base.relative_to(root).as_posix() if base != root else "."),
            "files": sorted(files),
            "dirs": sorted(dirs),
        }
        return json.dumps(payload)

    return list_files
