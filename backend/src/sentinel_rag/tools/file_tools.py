from __future__ import annotations

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
