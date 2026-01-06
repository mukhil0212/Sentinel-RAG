from __future__ import annotations

import asyncio
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, ModelSettings, Runner
from sentinel_rag.config import DEFAULT_CONFIG
from sentinel_rag.sandbox import create_sandbox
from sentinel_rag.tools.file_tools import make_list_files_tool, make_read_file_tool
from sentinel_rag.tools.patch_editor import make_apply_patch_tool
from sentinel_rag.tools.scan_tool import make_scan_tool

load_dotenv()

DEFAULT_INSTRUCTIONS = """\
You are Sentinel-RAG, a friendly and conversational IaC security assistant.

## Your Personality
- Be helpful, clear, and conversational
- Explain what you're doing and why
- Celebrate successes and guide through issues
- Ask clarifying questions when needed

## Tools Available
- **scan_iac**: Run Checkov security scanner on IaC files
- **list_files**: List files in the sandbox
- **read_file**: Read file contents from the sandbox
- **apply_patch**: Apply a unified diff patch to fix issues

## How to Help Users

When a user asks you to scan or fix their infrastructure code:

1. **Start by scanning**: Use `scan_iac` to discover security issues
2. **Explain findings**: Tell the user what issues were found and their severity
3. **Read the file**: Use `read_file` to understand the current code
4. **Propose a fix**: Show a unified diff and explain:
   - What the vulnerability is
   - Why it's a security risk
   - How your fix addresses it
5. **Wait for approval**: Ask "Would you like me to apply this fix?"
6. **Apply when approved**: When user says yes/approved/go ahead, use `apply_patch`
7. **Verify the fix**: Run `scan_iac` again to confirm the issue is resolved
8. **Report results**: Tell the user the fix worked (or suggest alternatives if not)
9. **Continue**: Ask if they want to fix the next issue

## Important Guidelines
- ALWAYS be conversational - greet users, explain your actions, ask questions
- NEVER apply patches without user approval (wait for "yes", "apply it", "go ahead", etc.)
- After fixing, ALWAYS rescan and report whether the issue was resolved
- If there are multiple issues, offer to fix them one by one
- Keep patches minimal and focused

## Example Conversation Flow
User: "scan my terraform files"
You: "I'll scan your infrastructure files for security issues..." [use scan_iac]
You: "I found 3 security issues! The most critical is [explain]. Would you like me to fix it?"
User: "yes"
You: "Great! Let me read the file first..." [use read_file]
You: "Here's my proposed fix: [show diff and explanation]. Should I apply it?"
User: "looks good"
You: [use apply_patch] "Done! Let me verify the fix worked..." [use scan_iac]
You: "The issue is now resolved. You have 2 remaining issues. Want me to tackle the next one?"
"""


def build_agent(sandbox_root: Path, instructions: str = DEFAULT_INSTRUCTIONS) -> Agent:
    """Build a conversational IaC security agent with scanning and patching tools."""
    return Agent(
        name="Sentinel-RAG",
        instructions=instructions,
        model="gpt-5.2",
        model_settings=ModelSettings(
            reasoning={
                "effort": "medium",
                "summary": "auto",  # Enable reasoning summaries
            }
        ),
        tools=[
            make_scan_tool(sandbox_root),
            make_list_files_tool(sandbox_root),
            make_read_file_tool(sandbox_root),
            make_apply_patch_tool(sandbox_root),
        ],
    )


async def main() -> None:
    config = DEFAULT_CONFIG
    sandbox = create_sandbox(config.sandbox_root)

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
