"""Model, Portkey, paths, and the team's safety limits.

Every agent uses gpt-6-luna through Portkey. The key is read from the
PORTKEY_API_KEY environment variable (a .env in this project or any parent
folder is loaded first); it is never printed or stored.

gpt-6-luna needs the Responses API for function tools, so we use
OpenAIResponsesModel rather than the chat-completions model.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import UsageLimits
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent  # HW 5/
for folder in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=False)

# ---------- paths ----------
PROMPTS_DIR = BACKEND_DIR / "prompts"
DB_PATH = PROJECT_ROOT / "data" / "campus_customs_new.db"  # only used to hash it; agents read it via MCP
AUDIT_PATH = PROJECT_ROOT / "output" / "audit_trail.json"
MCP_SERVER_DIR = PROJECT_ROOT / "mcp_server"
MCP_SERVER_SCRIPT = MCP_SERVER_DIR / "mcp_server.py"
_MCP_VENV_PYTHON = MCP_SERVER_DIR / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
# Use mcp_server/.venv if it exists; otherwise this Python (fastmcp is in requirements.txt).
MCP_PYTHON = _MCP_VENV_PYTHON if _MCP_VENV_PYTHON.exists() else Path(sys.executable)

# ---------- model ----------
MODEL_NAME = "gpt-6-luna"  # the only model this team uses
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# ---------- safety limits (token and loop guardrails) ----------
MAX_DELEGATION_DEPTH = 2         # boss -> specialist -> one more specialist, no deeper
MAX_DELEGATIONS_PER_TICKET = 6   # total hand-offs the whole team may make on one ticket
MAX_STEPS_PER_AGENT = 14         # agent-loop nodes per agent run (about 6 model calls)
MAX_OUTPUT_TOKENS = 2500         # cap on each model response (includes reasoning tokens)
TEAM_LIMITS = UsageLimits(       # shared by every agent working the same ticket
    request_limit=30,
    tool_calls_limit=45,
    total_tokens_limit=300_000,
)
AUDIT_TEXT_LIMIT = 4000          # longest text kept per audit field


def model_settings() -> OpenAIResponsesModelSettings:
    return OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS, openai_reasoning_effort="low")


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Put it in a .env in this project or a parent folder.")
    return key


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    client = AsyncOpenAI(
        api_key=require_api_key(),
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
