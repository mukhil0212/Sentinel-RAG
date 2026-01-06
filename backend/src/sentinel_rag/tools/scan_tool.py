from __future__ import annotations

from pathlib import Path

from agents import function_tool

from sentinel_rag.scanners.checkov_scanner import scan_checkov
from sentinel_rag.scanners.tflint_scanner import scan_tflint


def make_scan_tool(sandbox_root: Path):
    """Create a scan_iac tool bound to a specific sandbox root."""
    sandbox_root = sandbox_root.resolve()

    @function_tool
    def scan_iac(file_path: str | None = None) -> str:
        """Run security scanners on IaC files in the sandbox.

        Use this tool to:
        - Discover security issues in Terraform/CloudFormation/K8s manifests
        - Verify that a fix resolved an issue (rescan after applying a patch)
        - Get a prioritized list of findings to address

        Scanners used:
        - Checkov: Comprehensive policy-as-code scanner (1000+ policies)
        - tflint: Terraform linter for best practices

        Args:
            file_path: Optional path to a specific file to scan.
                       If None, scans all IaC files in the sandbox.

        Returns:
            A formatted report of findings sorted by severity.
        """
        scanner_notes: list[str] = []

        # Run Checkov (primary security scanner)
        checkov_target: str | None = None
        if file_path:
            target = (sandbox_root / file_path).resolve()
            if target.exists() and target.is_dir():
                checkov_target = file_path
        checkov_findings, checkov_run = scan_checkov(sandbox_root, checkov_target)
        if checkov_run.exit_code not in (0, 1):  # 0=pass, 1=failures found
            scanner_notes.append(f"Checkov error (exit {checkov_run.exit_code}): {checkov_run.stderr[:200]}")

        # Run tflint for Terraform-specific linting
        tflint_findings, tflint_run = scan_tflint(sandbox_root)
        if tflint_run.exit_code not in (0, 2):  # 0=pass, 2=issues found
            scanner_notes.append(f"tflint error (exit {tflint_run.exit_code}): {tflint_run.stderr[:200]}")

        all_findings = [*checkov_findings, *tflint_findings]

        # Filter to specific file if requested
        if file_path:
            all_findings = [f for f in all_findings if f.file_path and file_path in f.file_path]

        # Deduplicate by finding ID
        seen_ids: set[str] = set()
        unique_findings = []
        for f in all_findings:
            if f.id not in seen_ids:
                seen_ids.add(f.id)
                unique_findings.append(f)
        all_findings = unique_findings

        if not all_findings:
            msg = f"No security issues found in {file_path}." if file_path else "No security issues found in the sandbox."
            if scanner_notes:
                msg += "\n\nScanner notes:\n" + "\n".join(scanner_notes)
            return msg

        # Sort by severity priority
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        all_findings.sort(key=lambda f: severity_order.get(f.severity.lower(), 5))

        # Format findings as a readable report
        lines = [f"Found {len(all_findings)} issue(s):\n"]
        for i, finding in enumerate(all_findings, 1):
            location = f"{finding.file_path}"
            if finding.line:
                location += f":{finding.line}"
            lines.append(
                f"{i}. [{finding.severity.upper()}] {finding.title}\n"
                f"   Tool: {finding.tool}\n"
                f"   File: {location}\n"
                f"   {finding.description}\n"
                f"   Recommendation: {finding.recommendation}\n"
            )

        if scanner_notes:
            lines.append("\nScanner notes:\n" + "\n".join(scanner_notes))

        return "\n".join(lines)

    return scan_iac
