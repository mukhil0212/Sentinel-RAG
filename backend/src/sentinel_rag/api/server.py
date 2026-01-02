from __future__ import annotations

from typing import Any
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from pydantic import BaseModel

from sentinel_rag.config import DEFAULT_CONFIG
from sentinel_rag.sandbox import create_sandbox
from sentinel_rag.agents.agent_service import build_agent
from agents import Runner
from agents.stream_events import RawResponsesStreamEvent
from sentinel_rag.agents.agent_service import build_agent

app = FastAPI(title="Sentinel-RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
SESSIONS: dict[str, dict[str, Any]] = {}


def extract_unified_diff(text: str) -> str | None:
    if "```" in text:
        parts = text.split("```")
        for i in range(len(parts) - 1):
            header = parts[i].strip().lower()
            body = parts[i + 1]
            if header.endswith("diff"):
                return body.strip("\n")

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("diff --git") or line.startswith("--- "):
            return "\n".join(lines[idx:]).strip()

    return None


class SessionCreateResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    session_id: str
    message: str


class MessageResponse(BaseModel):
    text: str
    diff: str | None = None


class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool
    reason: str | None = None


@app.post("/api/session", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    """Create a sandboxed session and return its ID."""
    session_id = uuid.uuid4().hex
    sandbox = create_sandbox(DEFAULT_CONFIG.repo_root, DEFAULT_CONFIG.sandbox_root)
    SESSIONS[session_id] = {
        "sandbox_root": str(sandbox.root),
        "previous_response_id": None,
        "last_diff": None,
    }
    return SessionCreateResponse(session_id=session_id)



@app.post("/api/approve", response_model=MessageResponse)
async def approve_patch(payload: ApprovalRequest) -> MessageResponse:
    """Apply the last proposed diff if approved, or re-propose on rejection."""
    session = SESSIONS.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    sandbox_root = Path(session["sandbox_root"])
    agent = build_agent(sandbox_root)

    if payload.approved:
        diff = session.get("last_diff")
        if not diff:
            raise HTTPException(status_code=400, detail="No proposed diff to apply")
        prompt = (
            "User approved. Apply this exact diff using apply_patch.\n\n"
            f"Approved diff:\n{diff}"
        )
        result = await Runner.run(
            agent,
            input=prompt,
            previous_response_id=session.get("previous_response_id"),
        )
        text = str(result.final_output)
        session["previous_response_id"] = result.last_response_id
        return MessageResponse(text=text, diff=diff)

    reason = payload.reason or "No reason provided."
    prompt = (
        "User rejected the prior proposal. "
        f"Reason: {reason}\n\n"
        "Propose an alternative minimal diff and rationale. "
        "Do not apply any patch."
    )
    result = await Runner.run(
        agent,
        input=prompt,
        previous_response_id=session.get("previous_response_id"),
    )
    text = str(result.final_output)
    diff = extract_unified_diff(text)
    session["previous_response_id"] = result.last_response_id
    session["last_diff"] = diff
    return MessageResponse(text=text, diff=diff)


@app.post("/api/message/stream")
async def send_message_stream(payload: MessageRequest) -> StreamingResponse:
    """Stream an agent response as SSE events."""
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
                    lines = delta.split("\n")
                    for line in lines:
                        yield f"data: {line}\n"
                    yield "\n"

        text = str(result.final_output)
        diff = extract_unified_diff(text)
        session["previous_response_id"] = result.last_response_id
        session["last_diff"] = diff

        final_payload = {
            "final_output": text,
            "diff": diff,
            "last_response_id": result.last_response_id,
        }
        yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
