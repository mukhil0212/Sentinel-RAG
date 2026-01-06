from __future__ import annotations

import json
from pathlib import Path

from sentinel_rag.scanners.command_runner import CommandResult, run_command
from sentinel_rag.scanners.models import Finding


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


def scan_checkov(sandbox_root: Path, file_path: str | None = None) -> tuple[list[Finding], CommandResult]:
    """Run Checkov on the sandbox and return normalized findings.

    Checkov supports Terraform, CloudFormation, Kubernetes, Helm, ARM, and more.
    Requires `checkov` to be installed: pip install checkov

    Args:
        sandbox_root: Path to the sandbox directory
        file_path: Optional specific file to scan (relative to sandbox)
    """
    cmd = [
        "checkov",
        "--output", "json",
        "--compact",
        "--quiet",
    ]

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
            check_name = check.get("check", "Unknown check")
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
                    description=check.get("check_result", {}).get("evaluated_keys", [])
                                if isinstance(check.get("check_result"), dict)
                                else str(check_name),
                    recommendation=guideline or f"See Checkov docs for {check_id}",
                    file_path=file_path_result or None,
                    line=int(line) if line else None,
                    raw=check,
                )
            )

    return findings, result
