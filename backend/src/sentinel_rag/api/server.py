from __future__ import annotations

from typing import Any
import uuid
from pathlib import Path
import json
import shutil
import sys
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

from sentinel_rag.config import DEFAULT_CONFIG
from sentinel_rag.sandbox import create_sandbox
from sentinel_rag.agents.agent_service import build_agent
from sentinel_rag.scanners.checkov_scanner import _resolve_checkov_command
from agents import Runner
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from agents.items import ToolCallItem, ToolCallOutputItem, ReasoningItem
from sentinel_rag.store.supabase_store import SupabaseConversationStore, MessageRecord

load_dotenv()

app = FastAPI(title="Sentinel-RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    store = SupabaseConversationStore()
except Exception:
    store = None

SESSIONS: dict[str, dict[str, Any]] = {}


class SessionCreateResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    session_id: str
    message: str


class FileUpsertRequest(BaseModel):
    session_id: str
    path: str
    content: str


class FileUpsertResponse(BaseModel):
    ok: bool
    path: str


class FileReadRequest(BaseModel):
    session_id: str
    path: str


class FileReadResponse(BaseModel):
    ok: bool
    path: str
    content: str


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    children: list["FileNode"] | None = None


class FileListRequest(BaseModel):
    session_id: str


class FileListResponse(BaseModel):
    ok: bool
    files: list[FileNode]


class FileDeleteRequest(BaseModel):
    session_id: str
    path: str


class FileDeleteResponse(BaseModel):
    ok: bool
    path: str


def _sse_data(text: str) -> str:
    lines = text.split("\n")
    return "".join([f"data: {line}\n" for line in lines]) + "\n"


def _sse_json(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\n" + _sse_data(json.dumps(payload, default=str))


def _tool_call_payload(item: ToolCallItem) -> dict[str, Any]:
    raw = item.raw_item
    if isinstance(raw, dict):
        return {
            "type": raw.get("type"),
            "name": raw.get("name"),
            "call_id": raw.get("call_id"),
            "arguments": raw.get("arguments"),
        }
    return {
        "type": getattr(raw, "type", None),
        "name": getattr(raw, "name", None),
        "call_id": getattr(raw, "call_id", None),
        "arguments": getattr(raw, "arguments", None),
    }


def _tool_output_payload(item: ToolCallOutputItem) -> dict[str, Any]:
    output = item.output
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    return {
        "type": getattr(item.raw_item, "type", None) if not isinstance(item.raw_item, dict) else item.raw_item.get("type"),
        "call_id": getattr(item.raw_item, "call_id", None) if not isinstance(item.raw_item, dict) else item.raw_item.get("call_id"),
        "output": output,
    }


@app.post("/api/session", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    """Create a sandboxed session and return its ID."""
    session_id = store.create_session().session_id if store else uuid.uuid4().hex
    sandbox = create_sandbox(DEFAULT_CONFIG.sandbox_root)
    SESSIONS[session_id] = {
        "sandbox_root": str(sandbox.root),
        "previous_response_id": None,
    }
    return SessionCreateResponse(session_id=session_id)


@app.get("/api/debug/env")
async def debug_env() -> dict[str, Any]:
    """Lightweight runtime diagnostics (intended for local dev)."""
    try:
        import sentinel_rag as sentinel_rag_pkg
        sentinel_rag_file = getattr(sentinel_rag_pkg, "__file__", None)
    except Exception:
        sentinel_rag_file = None

    resolved = _resolve_checkov_command()
    resolved_path = resolved[0] if resolved else None
    return {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "sys_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "sentinel_rag_file": sentinel_rag_file,
        "checkov_which": shutil.which("checkov"),
        "checkov_resolved": resolved,
        "checkov_resolved_exists": bool(resolved_path and Path(resolved_path).exists()),
    }


@app.post("/api/chat")
async def chat(payload: MessageRequest) -> StreamingResponse:
    """Stream a conversational agent response. Single endpoint for all interactions."""
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"])
    agent = build_agent(sandbox_root)

    async def event_stream():
        result = Runner.run_streamed(
            agent,
            input=payload.message,
            previous_response_id=session.get("previous_response_id"),
        )

        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                event_data = event.data
                event_type = None
                delta = None
                if isinstance(event_data, dict):
                    event_type = event_data.get("type")
                    delta = event_data.get("delta")
                else:
                    event_type = getattr(event_data, "type", None)
                    delta = getattr(event_data, "delta", None)

                if event_type == "response.output_text.delta" and isinstance(delta, str):
                    yield _sse_data(delta)

            elif isinstance(event, RunItemStreamEvent):
                if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
                    yield _sse_json("tool_called", _tool_call_payload(event.item))
                elif event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
                    yield _sse_json("tool_output", _tool_output_payload(event.item))
                elif isinstance(event.item, ReasoningItem):
                    # Extract reasoning summary
                    raw = event.item.raw_item
                    summary = None
                    if isinstance(raw, dict):
                        summary_list = raw.get("summary", [])
                        if summary_list:
                            summary = "\n".join(s.get("text", "") for s in summary_list if isinstance(s, dict))
                    else:
                        summary_list = getattr(raw, "summary", [])
                        if summary_list:
                            summary = "\n".join(getattr(s, "text", "") for s in summary_list)
                    if summary:
                        yield _sse_json("reasoning", {"summary": summary})

        text = str(result.final_output)
        session["previous_response_id"] = result.last_response_id

        if store:
            store.add_message(
                MessageRecord(session_id=payload.session_id, role="user", content=payload.message)
            )
            store.add_message(
                MessageRecord(session_id=payload.session_id, role="assistant", content=text)
            )

        final_payload = {
            "final_output": text,
            "last_response_id": result.last_response_id,
        }
        yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/file/upsert", response_model=FileUpsertResponse)
async def upsert_file(payload: FileUpsertRequest) -> FileUpsertResponse:
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"]).resolve()
    target = (sandbox_root / payload.path).resolve()
    try:
        target.relative_to(sandbox_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes sandbox root") from None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return FileUpsertResponse(ok=True, path=payload.path)


@app.post("/api/file/read", response_model=FileReadResponse)
async def read_file(payload: FileReadRequest) -> FileReadResponse:
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"]).resolve()
    target = (sandbox_root / payload.path).resolve()
    try:
        target.relative_to(sandbox_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes sandbox root") from None

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileReadResponse(ok=True, path=payload.path, content=target.read_text(encoding="utf-8"))


def _build_file_tree(root: Path, base: Path) -> list[FileNode]:
    """Recursively build file tree for sandbox."""
    nodes: list[FileNode] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return nodes

    for entry in entries:
        if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules", ".terraform"):
            continue

        rel_path = entry.relative_to(base).as_posix()
        if entry.is_dir():
            children = _build_file_tree(entry, base)
            nodes.append(FileNode(name=entry.name, path=rel_path, is_dir=True, children=children))
        else:
            nodes.append(FileNode(name=entry.name, path=rel_path, is_dir=False))
    return nodes


@app.post("/api/file/list", response_model=FileListResponse)
async def list_files(payload: FileListRequest) -> FileListResponse:
    """List all files in the session sandbox."""
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"]).resolve()
    files = _build_file_tree(sandbox_root, sandbox_root)
    return FileListResponse(ok=True, files=files)


@app.post("/api/file/delete", response_model=FileDeleteResponse)
async def delete_file(payload: FileDeleteRequest) -> FileDeleteResponse:
    """Delete a file from the sandbox."""
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"]).resolve()
    target = (sandbox_root / payload.path).resolve()

    try:
        target.relative_to(sandbox_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes sandbox root") from None

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if target.is_dir():
        import shutil
        shutil.rmtree(target)
    else:
        target.unlink()

    return FileDeleteResponse(ok=True, path=payload.path)
