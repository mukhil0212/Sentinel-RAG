from __future__ import annotations

import asyncio
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, ModelSettings, Runner
from sentinel_rag.config import DEFAULT_CONFIG
from sentinel_rag.sandbox import create_sandbox
from sentinel_rag.tools.file_tools import make_read_file_tool
from sentinel_rag.tools.patch_editor import make_apply_patch_tool

load_dotenv()  # Pull API keys/config from backend/.env into the process env.
DEFAULT_INSTRUCTIONS = (
    "You are Sentinel-RAG, an IaC autofix agent. "
    "Always read relevant files before patching. "
    "First propose the minimal fix as a unified diff and wait for confirmation. "
    "Only use apply_patch after the user explicitly approves. "
    "Use the apply_patch tool for edits and keep changes minimal. "
    "Return a short summary of the change."
)

def build_agent(sandbox_root: Path, instructions=DEFAULT_INSTRUCTIONS) -> Agent:
    # Build a single agent that can read and apply patches inside the sandbox.
    return Agent(
        name="Sentinel-RAG",
        instructions=instructions,
        model="gpt-5.2",
        model_settings=ModelSettings(
            reasoning={"effort": "low"},
        ),
        tools=[
            make_read_file_tool(sandbox_root),
            make_apply_patch_tool(sandbox_root, auto_approve=True),
        ],
    )


async def main() -> None:
    config = DEFAULT_CONFIG
    # Work in an isolated copy of the repo to avoid touching the real workspace.
    sandbox = create_sandbox(config.repo_root, config.sandbox_root)

    # Seed a tiny file so we can verify the patch flow end-to-end.
    demo_path = sandbox.root / "demo.txt"
    demo_path.write_text("status = broken\n", encoding="utf-8")

    agent = build_agent(sandbox.root)
    prompt = (
        "Fix demo.txt by changing 'status = broken' to 'status = fixed'. "
        "Read the file first, then apply a minimal patch."
    )

    result = await Runner.run(agent, input=prompt)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
