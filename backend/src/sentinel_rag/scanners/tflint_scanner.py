from __future__ import annotations

import json
from pathlib import Path

from sentinel_rag.scanners.command_runner import CommandResult, run_command
from sentinel_rag.scanners.models import Finding


def _severity_from_tflint(issue: dict) -> str:
    # tflint doesn't always report a severity; default to "medium".
    sev = issue.get("severity")
    if isinstance(sev, str) and sev:
        return sev.lower()
    return "medium"


def scan_tflint(sandbox_root: Path) -> tuple[list[Finding], CommandResult]:
    """Run tflint in the sandbox and return normalized findings.

    Requires `tflint` to be installed and on PATH.
    """
    result = run_command(["tflint", "--format", "json"], cwd=sandbox_root, timeout_s=180)

    findings: list[Finding] = []
    # tflint exit codes: 0 OK, 2 issues found, others are errors.
    # Even on errors, tflint may still emit structured JSON we can surface.

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return findings, result

    for err in payload.get("errors", []) or []:
        rng = err.get("range") or {}
        filename = rng.get("filename")
        start = (rng.get("start") or {}).get("line")
        finding_id = f"tflint:error:{filename or 'unknown'}:{start or 0}"
        findings.append(
            Finding(
                id=finding_id,
                tool="tflint",
                severity=(err.get("severity") or "error").lower(),
                title=err.get("summary") or "tflint error",
                description=err.get("message") or "",
                recommendation="Fix Terraform/HCL syntax so scanners can run.",
                file_path=filename,
                line=int(start) if isinstance(start, int) else None,
                raw=err,
            )
        )

    for issue in payload.get("issues", []) or []:
        rule = issue.get("rule") or {}
        rule_name = rule.get("name") or "unknown_rule"
        message = issue.get("message") or ""
        rng = issue.get("range") or {}
        filename = rng.get("filename")
        start = (rng.get("start") or {}).get("line")

        finding_id = f"tflint:{rule_name}:{filename or 'unknown'}:{start or 0}"
        findings.append(
            Finding(
                id=finding_id,
                tool="tflint",
                severity=_severity_from_tflint(issue),
                title=f"tflint: {rule_name}",
                description=message,
                recommendation=rule.get("link") or "Follow the tflint rule guidance.",
                file_path=filename,
                line=int(start) if isinstance(start, int) else None,
                raw=issue,
            )
        )

    return findings, result
