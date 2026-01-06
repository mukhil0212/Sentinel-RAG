from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from dotenv import load_dotenv
from agents import Runner
from agents.stream_events import RawResponsesStreamEvent

from sentinel_rag.config import DEFAULT_CONFIG
from sentinel_rag.sandbox import create_sandbox
from sentinel_rag.agents.agent_service import build_agent


load_dotenv()  # Pull API keys/config from backend/.env into the process env.


def _extract_text_delta(event_data) -> str | None:
    event_type = None
    delta = None
    if isinstance(event_data, dict):
        event_type = event_data.get("type")
        delta = event_data.get("delta")
    else:
        event_type = getattr(event_data, "type", None)
        delta = getattr(event_data, "delta", None)

    if event_type == "response.output_text.delta" and isinstance(delta, str):
        return delta
    return None


async def run_streamed(agent, prompt: str, previous_response_id: str | None):
    result = Runner.run_streamed(
        agent,
        input=prompt,
        previous_response_id=previous_response_id,
    )
    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            chunk = _extract_text_delta(event.data)
            if chunk:
                print(chunk, end="", flush=True)

    print()
    return result


def seed_demo_files(sandbox_root: Path) -> None:
    main_tf = sandbox_root / "main.tf"
    main_tf.write_text(
        "\n".join(
            [
                "terraform {",
                "  required_version = \">= 1.5.0\"",
                "}",
                "",
                "provider \"aws\" {",
                "  region = \"us-east-1\"",
                "}",
                "",
                "resource \"aws_s3_bucket\" \"logs\" {",
                "  bucket = \"sentinel-demo-logs\"",
                "  acl    = \"public-read\"",
                "}",
                "",
                "resource \"aws_security_group\" \"web\" {",
                "  name   = \"web-sg\"",
                "  vpc_id = \"vpc-123456\"",
                "",
                "  ingress {",
                "    from_port   = 80",
                "    to_port     = 80",
                "    protocol    = \"tcp\"",
                "    cidr_blocks = [\"0.0.0.0/0\"]",
                "  }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )


async def main() -> None:
    config = DEFAULT_CONFIG
    sandbox = create_sandbox(config.sandbox_root)
    seed_demo_files(sandbox.root)

    agent = build_agent(sandbox.root)
    previous_response_id: str | None = None

    print("\nChat mode. Type /quit to exit.")
    print("Seeded sandbox file: main.tf")

    try:
        while True:
            user_input = input("\nYou> ").strip()
            if not user_input:
                continue
            if user_input == "/quit":
                break

            result = await run_streamed(agent, user_input, previous_response_id)
            previous_response_id = result.last_response_id
    finally:
        shutil.rmtree(sandbox.root, ignore_errors=True)
        print(f"\n[cleanup] Removed sandbox {sandbox.root}")


if __name__ == "__main__":
    asyncio.run(main())
