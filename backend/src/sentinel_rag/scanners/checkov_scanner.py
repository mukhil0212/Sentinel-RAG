from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

from sentinel_rag.scanners.command_runner import CommandResult, run_command
from sentinel_rag.scanners.models import Finding


def _resolve_checkov_command() -> list[str]:
    """Return a runnable Checkov command, even when PATH is not configured.

    Preference order:
    0) `SENTINEL_RAG_CHECKOV_BIN` explicit override
    1) `checkov` found on PATH
    2) `checkov` next to the running Python interpreter (venv-local bin/Scripts)
    3) repo-local virtualenv script (common in local dev)
    4) `python -m checkov` if the module is importable
    """
    override = os.environ.get("SENTINEL_RAG_CHECKOV_BIN")
    if override:
        return [override]

    on_path = shutil.which("checkov")
    if on_path:
        return [on_path]

    # In venvs, console scripts live next to sys.executable.
    exe_dir = Path(sys.executable).resolve().parent
    candidate = exe_dir / "checkov"
    if candidate.exists():
        return [str(candidate)]
    candidate_win = exe_dir / "checkov.exe"
    if candidate_win.exists():
        return [str(candidate_win)]

    # Local dev convenience: if the repo contains a venv, use it.
    # This helps when the API is started outside the venv but Checkov is installed inside it.
    backend_dir = Path(__file__).resolve().parents[3]  # .../backend
    repo_dir = backend_dir.parent
    dev_candidates = [
        backend_dir / ".venv" / "bin" / "checkov",
        backend_dir / ".venv" / "Scripts" / "checkov.exe",
        repo_dir / ".venv" / "bin" / "checkov",
        repo_dir / ".venv" / "Scripts" / "checkov.exe",
    ]
    for p in dev_candidates:
        if p.exists():
            return [str(p)]

    # Last resort: run as module if installed but scripts weren't exposed.
    if importlib.util.find_spec("checkov") is not None:
        return [sys.executable, "-m", "checkov"]

    return ["checkov"]


def _severity_from_checkov(severity: str | None) -> str:
    """Normalize Checkov severity to our standard."""
    if not severity:
        return "medium"
    sev = severity.upper()
    if sev == "CRITICAL":
        return "critical"
    if sev == "HIGH":
        return "high"
    if sev == "MEDIUM":
        return "medium"
    if sev == "LOW":
        return "low"
    return "info"


def _description_from_checkov(check: dict) -> str:
    check_name = check.get("check_name") or check.get("check") or "Unknown check"
    check_result = check.get("check_result")
    if isinstance(check_result, dict):
        evaluated_keys = check_result.get("evaluated_keys")
        if isinstance(evaluated_keys, list):
            keys = [str(k) for k in evaluated_keys if k is not None]
            if len(keys) > 20:
                keys = [*keys[:20], "... (truncated)"]
            if keys:
                return "Evaluated keys:\n" + "\n".join(f"- {k}" for k in keys)

    message = check.get("message") or check.get("description")
    return str(message or check_name)


def scan_checkov(
    sandbox_root: Path,
    file_path: str | None = None,
    frameworks: list[str] | None = None,
) -> tuple[list[Finding], CommandResult]:
    """Run Checkov on the sandbox and return normalized findings.

    Checkov supports Terraform, CloudFormation, Kubernetes, Helm, ARM, and more.
    Requires `checkov` to be installed: pip install checkov

    Args:
        sandbox_root: Path to the sandbox directory
        file_path: Optional specific file to scan (relative to sandbox)
        frameworks: Optional Checkov frameworks to restrict scanning to
    """
    cmd = [
        *_resolve_checkov_command(),
        "--output", "json",
        "--compact",
        "--quiet",
    ]

    # If frameworks are set, Checkov will only scan those.
    # Example: --framework terraform kubernetes
    if frameworks:
        cmd.extend(["--framework", *frameworks])

    if file_path:
        target = sandbox_root / file_path
        if target.is_file():
            cmd.extend(["--file", str(target)])
        else:
            cmd.extend(["--directory", str(target)])
    else:
        cmd.extend(["--directory", str(sandbox_root)])

    result = run_command(cmd, cwd=sandbox_root, timeout_s=300)

    findings: list[Finding] = []

    # Checkov outputs JSON to stdout
    # Exit code 1 = checks failed, 0 = all passed, other = error
    if not result.stdout:
        return findings, result

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return findings, result

    # Checkov returns a list of check results per framework
    # Each framework result has "passed_checks", "failed_checks", "skipped_checks"
    results_list = payload if isinstance(payload, list) else [payload]

    for framework_result in results_list:
        if not isinstance(framework_result, dict):
            continue

        check_type = framework_result.get("check_type", "unknown")
        failed_checks = framework_result.get("results", {}).get("failed_checks", [])

        for check in failed_checks:
            check_id = check.get("check_id", "unknown")
            check_name = check.get("check_name") or check.get("check") or "Unknown check"
            file_path_result = check.get("file_path", "")
            file_line_range = check.get("file_line_range", [])
            guideline = check.get("guideline", "")
            severity = check.get("severity")

            # Normalize file path (remove leading /)
            if file_path_result.startswith("/"):
                file_path_result = file_path_result[1:]

            # Get line number
            line = None
            if file_line_range and len(file_line_range) >= 1:
                line = file_line_range[0]

            finding_id = f"checkov:{check_id}:{file_path_result}:{line or 0}"

            findings.append(
                Finding(
                    id=finding_id,
                    tool="checkov",
                    severity=_severity_from_checkov(severity),
                    title=f"{check_id}: {check_name}",
                    description=_description_from_checkov(check),
                    recommendation=str(guideline) if guideline else f"See Checkov docs for {check_id}",
                    file_path=file_path_result or None,
                    line=int(line) if line else None,
                    raw=check,
                )
            )

    return findings, result
