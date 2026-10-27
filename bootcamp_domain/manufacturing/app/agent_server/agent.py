"""Fjällmark Manufacturing router agent: one chat entry point for the Manufacturing Analyst Genie Agent of this sample.

Based on the Databricks app template ``agent-openai-advanced`` (OpenAI Agents SDK, short-term memory and
long-running background tasks in Lakebase). The router does not query data itself: it asks the Manufacturing Analyst
Genie Agent through its managed MCP server (``/api/2.0/mcp/genie/<space_id>``) and looks up business terms in
the official glossary that ships with the app (``glossary/glossary.csv`` + ``glossary/pages/*.md``).

The Genie calls run as the APP'S SERVICE PRINCIPAL (the template's default identity; the chat UI calls this
agent server without a user token). Unity Catalog governs that principal like any user: notebook
06_router_app grants it SELECT on the sample's gold schemas only and copies the deploying participant's rows of
the notebook 03 mapping table (governance.user_plant_access) to it, so the row filters and masks apply to every answer.
"""
import csv
import logging
import os
import re
import unicodedata
from contextlib import AsyncExitStack
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator

import mlflow
from agents import Agent, ModelSettings, Runner, function_tool, set_default_openai_api, set_default_openai_client
from agents.tracing import set_trace_processors
from databricks.sdk import WorkspaceClient
from databricks_openai import AsyncDatabricksOpenAI
from databricks_openai.agents import AsyncDatabricksSession, McpServer
from fastapi import HTTPException
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from agent_server.utils import (
    deduplicate_input,
    get_databricks_host_from_env,
    get_lakebase_access_error_message,
    get_session_id,
    lakebase_config,
    process_agent_stream_events,
)

# NOTE: this will work for all databricks models OTHER than GPT-OSS, which uses a slightly different API
set_default_openai_client(AsyncDatabricksOpenAI())
set_default_openai_api("chat_completions")
set_trace_processors([])  # only use mlflow for trace processing
mlflow.openai.autolog()
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT") or "databricks-claude-sonnet-5-5"
GENIE_TIMEOUT_SECONDS = 120.0   # a Genie answer can take tens of seconds
# Claude on Databricks returns reasoning blocks in the message content around tool calls, which the Agents SDK's
# chat-completions converter cannot read (pydantic "ResponseOutputText ... Input should be a valid string").
# "between_tools" is the endpoint's way to switch thinking off for this model.
MODEL_SETTINGS = ModelSettings(extra_body={"thinking": {"type": "between_tools"}})

# (environment variable with the space id, agent name, what it answers) - the env var is bound to the app's
# genie-manufacturing resource (app.yaml, notebooks/06_router_app.py)
DOMAIN_AGENTS = [
    ("GENIE_SPACE_MANUFACTURING", "Manufacturing Analyst",
     "plants and production lines: OEE, yield, scrap, downtime, on-time completion, late orders, yield loss reasons, batches, equipment, production cost variance"),
]

# The glossary of this sample (a copy of the Manufacturing pages of bootcamp/context/). Its SQL uses the placeholder
# <catalog>; CATALOG is set by notebook 06 at deployment (the participant's catalog).
GLOSSARY_DIR = Path(__file__).resolve().parent.parent / "glossary"
CATALOG = os.getenv("CATALOG", "").strip()

ROUTER_INSTRUCTIONS = """You are the Fjällmark Manufacturing router: the single entry point to the manufacturing data of Fjällmark Consumer
Goods AB, a fictional Nordic consumer-goods group (brands Björkö Pantry, Kallkälla, Mjuk Care; company codes SE01,
NO01, DK01, FI01, DE01, PL01; group currency EUR; data 2024-01 to 2026-09, September 2026 is the last closed month).

You never query data yourself. One Genie Agent does, curated on the governed manufacturing domain:
{agents}
You also have the tool lookup_glossary: the official Fjällmark Manufacturing glossary (definitions, business rules,
reference SQL).

How you work:
1. Before you answer a question that uses a business term (OEE, yield, scrap rate, downtime, schedule adherence, production cost variance, plant, production line, ...), look the term up
   with lookup_glossary and follow its definition and business rules. A question that asks what a term means or
   how it is calculated is answered from the glossary page; quote the definition, do not invent one. Call the
   tool without a term to see the list of terms.
2. For numbers, ask the Manufacturing Analyst a self-contained question with its query tool: name the period, the
   entity and the currency you need, and use the glossary's definition and vocabulary.
3. A query tool may return before the answer is ready (a status plus conversation_id and message_id): then call
   the matching poll tool until the answer is complete.
4. Use only numbers the analyst returned. Simple arithmetic on them (a difference, a share) is fine - show it.
   Never add or compare amounts of different currencies or definitions.
5. Reply with the answer first, then a short "Sources" line: the glossary page(s) you used and what the analyst
   answered, with the definition, period and currency it used.
6. You only cover manufacturing data. Decline questions about other domains (the official general-ledger revenue, COGS and margin, receivables, webshop orders and shoppers) politely, and point
   to the full Fjällmark bootcamp router (bootcamp/, with the Consumer, Finance and Manufacturing Analysts).
7. The analyst answers under Unity Catalog governance (row filters by plant, masked cost and personal data). Empty results or missing
   plants can be governance working as designed - say so instead of guessing. Never ask for or reveal personal data or masked cost figures.
{unavailable}"""


def _norm(text: str) -> str:
    """Lower-case, accents removed, every non-alphanumeric character a single space."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@lru_cache(maxsize=1)
def load_glossary() -> list[dict]:
    """The rows of glossary.csv, each with the names it is found by (term, term without '(...)', synonyms)."""
    with open(GLOSSARY_DIR / "glossary.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        names = [row["term"], re.sub(r"\s*\(.*?\)", "", row["term"]), *re.findall(r"\((.*?)\)", row["term"]),
                 *row.get("synonyms", "").split(";")]
        row["_names"] = sorted({n for n in (_norm(x) for x in names) if n}, key=len, reverse=True)
        row["_text"] = _norm(" ".join([row["term"], row.get("synonyms", ""), row.get("short_definition", "")]))
    return rows


def _score(query: str, row: dict) -> int:
    """How well a term matches: exact name > a name inside the question (or the question inside a name) > words."""
    if query in row["_names"]:
        return 1000
    padded = f" {query} "
    best = max((100 + len(n) for n in row["_names"] if f" {n} " in padded or f" {query} " in f" {n} "), default=0)
    if best:
        return best
    return sum(1 for word in query.split() if len(word) >= 3 and f" {word} " in f" {row['_text']} ")


def _with_catalog(text: str) -> str:
    return text.replace("<catalog>", CATALOG) if CATALOG else text


def _term_list(rows: list[dict]) -> str:
    return "\n".join(f"- {r['term']} ({r['subdomain']}): {r['short_definition']}" for r in rows)


@function_tool
def lookup_glossary(term: str = "") -> str:
    """Look up a business term in the official Fjällmark Manufacturing glossary.

    Returns the glossary page of the best matching term (definition, business rules, reference SQL, related
    tables), searched by term name and synonyms, case-insensitive. Without a term, or when nothing matches,
    returns the list of all terms with their short definitions.

    Args:
        term: the business term or synonym to look up, e.g. "OEE". Leave empty to list all terms.
    """
    rows = load_glossary()
    query = _norm(term)
    if not query:
        return f"The Manufacturing glossary has these terms:\n{_term_list(rows)}"
    ranked = sorted(((_score(query, r), r) for r in rows), key=lambda x: x[0], reverse=True)
    best_score, best = ranked[0]
    if best_score == 0:
        return (f"No glossary term matches {term!r}. The Manufacturing glossary has these terms:\n{_term_list(rows)}")
    page_file = GLOSSARY_DIR / "pages" / os.path.basename(best["page_path"])
    try:
        page = page_file.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Glossary page %s not found; returning the short definition.", page_file)
        page = f"# {best['term']}\n\n{best['short_definition']}\n\nRelated tables: {best['related_assets']}"
    others = [r["term"] for s, r in ranked[1:4] if s > 0]
    note = f"\n\n(Other terms that may be relevant: {', '.join(others)}.)" if others else ""
    if not CATALOG:
        note += "\n\n(CATALOG is not set: replace <catalog> with the participant's catalog.)"
    return f"Glossary page for {best['term']} (matched {term!r}):\n\n{_with_catalog(page)}{note}"


def init_genie_servers(workspace_client: WorkspaceClient) -> list[tuple[McpServer, str, str, str]]:
    """One managed Genie MCP server per configured domain agent: (server, name, scope, space_id)."""
    host = get_databricks_host_from_env()
    servers = []
    for env, name, scope in DOMAIN_AGENTS:
        space_id = os.getenv(env, "").strip()
        if not space_id:
            logger.warning("%s is not set; the %s is not available.", env, name)
            continue
        servers.append((McpServer(url=f"{host}/api/2.0/mcp/genie/{space_id}", name=name,
                                  workspace_client=workspace_client, timeout=GENIE_TIMEOUT_SECONDS,
                                  max_retry_attempts=1),
                        name, scope, space_id))
    return servers


async def connect_healthy_mcp_servers(
    stack: AsyncExitStack, servers: list[McpServer]
) -> tuple[list[McpServer], list[str]]:
    """Connect each MCP server and verify it can actually list its tools.

    The Agents SDK lists each server's tools lazily inside ``Runner.run``, so a server that
    connects but fails at list time (e.g. an unauthorized Genie space) would otherwise crash
    the whole request — including unrelated turns. We list tools here, per server: healthy
    servers are kept; any that fails to connect OR to list is dropped and its name returned,
    so the agent runs with whatever is available instead of erroring out.

    Returns (healthy_servers, unavailable_names).
    """
    healthy: list[McpServer] = []
    unavailable: list[str] = []
    for server in servers:
        name = getattr(server, "name", "MCP server")
        try:
            connected = await stack.enter_async_context(server)
            await connected.list_tools()  # forces the connectivity + authorization check now
            healthy.append(connected)
        except Exception:
            logger.warning("MCP server %r unavailable; continuing without it.", name, exc_info=True)
            unavailable.append(name)
    return healthy, unavailable


async def create_router(stack: AsyncExitStack) -> Agent:
    """The router agent with the glossary tool and the domain agent, when it is reachable."""
    configured = init_genie_servers(WorkspaceClient())   # the app's service principal
    healthy, unavailable = await connect_healthy_mcp_servers(stack, [s for s, *_ in configured])
    available = {getattr(s, "name", "") for s in healthy}
    agents = "\n".join(
        f"- {name} (tools query_space_{space_id} and poll_response_{space_id}): {scope}"
        for _, name, scope, space_id in configured if name in available) or "- (none reachable)"
    missing = [name for _, name, _ in DOMAIN_AGENTS if name not in available]
    note = (f"8. Not available right now: {', '.join(missing)}. Say so when a question needs numbers, "
            "and answer what the glossary can.") if missing else ""
    return Agent(
        name="Fjällmark Manufacturing router",
        instructions=ROUTER_INSTRUCTIONS.format(agents=agents, unavailable=note),
        model=LLM_ENDPOINT,
        model_settings=MODEL_SETTINGS,
        tools=[lookup_glossary],
        mcp_servers=healthy,
    )


def lakebase_session(request: ResponsesAgentRequest) -> AsyncDatabricksSession:
    """Session for stateful, short-term conversation history in the participant's Lakebase database."""
    session_id = get_session_id(request)
    if session_id:
        mlflow.update_current_trace(metadata={"mlflow.trace.session": session_id})
    return AsyncDatabricksSession(
        session_id=session_id,
        autoscaling_endpoint=lakebase_config.autoscaling_endpoint,
        project=lakebase_config.autoscaling_project,
        branch=lakebase_config.autoscaling_branch,
        schema=lakebase_config.memory_schema,
        create_tables=False,  # Tables created at startup in start_server.py
    )


def lakebase_error(e: Exception) -> HTTPException | None:
    error_msg = str(e).lower()
    if any(keyword in error_msg
           for keyword in ["lakebase", "pg_hba", "postgres", "database instance", "insufficient privilege"]):
        logger.error("Lakebase access error: %s", e)
        return HTTPException(status_code=503, detail=get_lakebase_access_error_message(lakebase_config.description))
    return None


@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    try:
        session = lakebase_session(request)
        # The router runs inside an AsyncExitStack so the Genie MCP server stays open for the whole request.
        async with AsyncExitStack() as stack:
            agent = await create_router(stack)
            messages = await deduplicate_input(request, session)
            result = await Runner.run(agent, messages, session=session)
        return ResponsesAgentResponse(
            output=[item.to_input_item() for item in result.new_items],
            custom_outputs={"session_id": session.session_id},
        )
    except Exception as e:
        if (http_error := lakebase_error(e)) is not None:
            raise http_error from e
        raise


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    try:
        session = lakebase_session(request)
        async with AsyncExitStack() as stack:
            agent = await create_router(stack)
            messages = await deduplicate_input(request, session)
            result = Runner.run_streamed(agent, input=messages, session=session)

            async for event in process_agent_stream_events(result.stream_events()):
                yield event
    except Exception as e:
        if (http_error := lakebase_error(e)) is not None:
            raise http_error from e
        raise
