from __future__ import annotations

from pathlib import Path

from agents import function_tool

from sentinel_rag.scanners.checkov_scanner import scan_checkov
from sentinel_rag.scanners.tflint_scanner import scan_tflint


_CHECKOV_FRAMEWORK_ALLOWLIST = {
    "terraform",
    "cloudformation",
    "kubernetes",
    "helm",
    "arm",
    "dockerfile",
    "secrets",
}


def _normalize_framework_hint(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return v if v in _CHECKOV_FRAMEWORK_ALLOWLIST else None


def _detect_checkov_frameworks(sandbox_root: Path) -> list[str]:
    """Best-effort framework detection from sandbox contents."""
    # Prefer Terraform when present (we also run tflint).
    for p in sandbox_root.rglob("*.tf"):
        if p.is_file():
            return ["terraform"]

    # Helm
    if (sandbox_root / "Chart.yaml").is_file() or any((sandbox_root / "charts").glob("*/Chart.yaml")):
        return ["helm"]

    # YAML-based (K8s/CloudFormation) heuristics: inspect a small sample.
    yaml_files: list[Path] = []
    for ext in ("*.yml", "*.yaml"):
        yaml_files.extend([p for p in sandbox_root.rglob(ext) if p.is_file()])
        if len(yaml_files) >= 5:
            break

    for p in yaml_files[:5]:
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
        except Exception:
            continue
        if "apiVersion:" in head and "kind:" in head:
            return ["kubernetes"]
        if "AWSTemplateFormatVersion" in head or "\nResources:" in head:
            return ["cloudformation"]

    return []


def make_scan_tool(sandbox_root: Path):
    """Create a scan_iac tool bound to a specific sandbox root."""
    sandbox_root = sandbox_root.resolve()

    @function_tool
    def scan_iac(file_path: str | None = None, iac_format: str | None = None) -> str:
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
            iac_format: Optional hint for the primary IaC type (e.g. "terraform", "kubernetes").
                        If provided, the tool will validate it and use it to narrow Checkov frameworks.

        Returns:
            A formatted report of findings sorted by severity.
        """
        scanner_notes: list[str] = []

        # Run Checkov (primary security scanner)
        framework_hint = _normalize_framework_hint(iac_format)
        if iac_format and not framework_hint:
            scanner_notes.append(f"Unrecognized iac_format '{iac_format}'. Falling back to auto-detection.")

        frameworks = [framework_hint] if framework_hint else _detect_checkov_frameworks(sandbox_root)
        if frameworks:
            scanner_notes.append(f"Checkov frameworks: {', '.join(frameworks)}")

        # For accuracy, prefer scanning the whole sandbox (cross-file checks), then filter if needed.
        checkov_scan_path: str | None = None
        if file_path:
            target = (sandbox_root / file_path).resolve()
            if target.exists() and target.is_dir():
                checkov_scan_path = file_path
        checkov_findings, checkov_run = scan_checkov(sandbox_root, checkov_scan_path, frameworks=frameworks or None)
        if checkov_run.exit_code not in (0, 1):  # 0=pass, 1=failures found
            scanner_notes.append(f"Checkov error (exit {checkov_run.exit_code}): {checkov_run.stderr[:200]}")

        # Run tflint for Terraform-specific linting
        tflint_findings = []
        tflint_run = None
        if not frameworks or "terraform" in frameworks:
            tflint_findings, tflint_run = scan_tflint(sandbox_root)
            if tflint_run.exit_code not in (0, 2):  # 0=pass, 2=issues found
                scanner_notes.append(f"tflint error (exit {tflint_run.exit_code}): {tflint_run.stderr[:200]}")
        else:
            scanner_notes.append("Skipped tflint (non-Terraform sandbox).")

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
