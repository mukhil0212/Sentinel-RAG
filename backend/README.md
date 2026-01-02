# Sentinel-RAG Backend

This backend hosts the Agents SDK harness for the Terraform autofix workflow.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Notes:
- The Agents SDK import path in code is `agents` (per the docs). If install fails, confirm the correct package name/version and update `pyproject.toml`.
- This repo pins the SDK to the GitHub main branch to pick up `ApplyPatchTool` and `agents.editor` APIs used by the official example.

## Demo

```bash
python3 -m sentinel_rag.workflows.demo_minimal
```

This runs a minimal agent that reads a toy file and applies a patch using the Agents SDK apply_patch tool.
