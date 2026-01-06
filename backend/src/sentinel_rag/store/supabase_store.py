from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from supabase import Client, create_client


@dataclass(frozen=True)
class SessionRecord:
    session_id: str


@dataclass(frozen=True)
class MessageRecord:
    session_id: str
    role: str
    content: str
    created_at: str | None = None


class SupabaseConversationStore:
    """Simple conversation store backed by Supabase."""

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self._url = url or os.environ.get("SUPABASE_URL")
        self._key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not self._url or not self._key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        self._client: Client = create_client(self._url, self._key)

    def create_session(self) -> SessionRecord:
        session_id = uuid.uuid4().hex
        payload = {"session_id": session_id}
        self._client.table("sessions").insert(payload).execute()
        return SessionRecord(session_id=session_id)

    def add_message(self, message: MessageRecord) -> None:
        payload = {
            "session_id": message.session_id,
            "role": message.role,
            "content": message.content,
        }
        self._client.table("messages").insert(payload).execute()

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        response = (
            self._client.table("messages")
            .select("session_id, role, content, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        records: list[MessageRecord] = []
        for item in response.data or []:
            records.append(
                MessageRecord(
                    session_id=item["session_id"],
                    role=item["role"],
                    content=item["content"],
                    created_at=item.get("created_at"),
                )
            )
        return records
