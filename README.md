# Sentinel‑RAG

Cursor for IaC security scans and autofixes.

IaC security scanning + autofix assistant with a per‑user sandbox, a chat UI, and a patch/diff workflow.

## How this is different from a “ChatGPT wrapper”

- **Real tools, not just chat**: runs actual scanners (Checkov, tflint) and returns structured findings.
- **Deterministic edits**: fixes are applied via a constrained `apply_patch` tool, with a diff you can review.
- **Workspace context**: the agent can list/read files inside a per‑session sandbox instead of relying on pasted snippets.
- **Isolation by design**: each user/session operates in its own sandbox directory (no access to the app’s codebase).
- **Auditable UX**: tool calls, outputs, and (summarized) reasoning are visible/expandable in the UI.

## What it does

- Creates a **per‑session sandbox** (an empty workspace) where users create and edit IaC files directly in a VS Code‑style editor.
- Runs **IaC scans** (currently Checkov + tflint where applicable).
- Lets the agent propose fixes and apply them via an `apply_patch` tool.
- Shows file edits in a **VS Code‑style diff viewer** (Monaco) and keeps tool/thinking output expandable in the chat.

## Repository layout

- `backend/`: FastAPI service + agent runtime (Agents SDK) + scanners/tools
- `frontend/`: Next.js app (chat UI + file tree + Monaco editor/diff)
- `.sentinel/sandboxes/`: per‑session sandboxes created at runtime (local dev)

## Prerequisites

- Python 3.11+ (backend venv)
- Node.js 18+ (frontend)
- Optional scanners:
  - `checkov` (for policy/security checks)
  - `tflint` (Terraform lint rules)

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
python -m sentinel_rag.api.server
```

Backend runs on `http://127.0.0.1:8000`.

Optional: install Checkov into the backend venv so the scanner can find it:

```bash
cd backend
source .venv/bin/activate
pip install checkov
checkov --version
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000` and talks to the backend at `http://127.0.0.1:8000`.

## Environment variables

Backend (optional, for persistence):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Scanner overrides (optional):

- `SENTINEL_RAG_CHECKOV_BIN`: absolute path to a `checkov` executable

## How scans work

- `scan_iac` tool runs:
  - **Checkov** if available (framework auto‑detected or hinted; runs across the sandbox and filters results back to the target file)
  - **tflint** when the sandbox contains Terraform (`.tf`) content

If Checkov is not found on PATH, the backend tries:
- venv/local `checkov`
- repo‑local `.venv` `checkov`
- `python -m checkov`
- `SENTINEL_RAG_CHECKOV_BIN` override

## Sandbox model

- Each chat session gets its own sandbox directory under `.sentinel/sandboxes/`.
- The sandbox starts **empty**; users create files directly in the VS Code‑style editor or load test templates.
- Tools (read/list/apply_patch/scan) are scoped to that sandbox root to avoid touching the app's source tree.

## Troubleshooting

- `checkov` “not found”: install it into `backend/.venv` (`pip install checkov`) or set `SENTINEL_RAG_CHECKOV_BIN`.
- Diff not appearing after `apply_patch`: ensure backend is running a version that emits `apply_patch` tool name and structured JSON outputs.

## Currently working

We’re working on integrating company best practices so the agent proposes fixes that match “how we do things here”, not generic advice:

- **Bring your standards into the assistant**: connect internal docs (runbooks, guidelines, exceptions, and patterns) so the agent can reference them while suggesting changes.
- **Context‑aware recommendations**: tailor suggestions to your environment and conventions (team/repo/project) instead of one‑size‑fits‑all outputs.
- **Explain “why” with references**: show which internal guideline influenced a recommendation so reviewers can trust and verify it.
- **Support different teams**: allow different orgs/teams to have different standards and preferences without conflicts.
- **Learn from decisions**: adapt over time based on what fixes are accepted/rejected so suggestions become more aligned with your workflow.
