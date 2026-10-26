"""Fjällmark router agent: one chat entry point for the bootcamp's three domain Genie Agents.

Based on the Databricks app template ``agent-openai-advanced`` (OpenAI Agents SDK, short-term memory and
long-running background tasks in Lakebase). The router does not query data itself: it asks the Consumer,
Finance and Manufacturing Analyst Genie Agents through their managed MCP servers
(``/api/2.0/mcp/genie/<space_id>``) and combines their answers.

The Genie calls run as the APP'S SERVICE PRINCIPAL (the template's default identity; the chat UI calls this
agent server without a user token). Unity Catalog governs that principal like any user: notebook
06_router_app grants it SELECT on the gold schemas only and maps it to the deploying participant's company codes
in the notebook 03 mapping table (no PII), so the row filters and column masks apply to every answer.
"""
import logging
import os
from contextlib import AsyncExitStack
from typing import AsyncGenerator

import mlflow
from agents import Agent, ModelSettings, Runner, set_default_openai_api, set_default_openai_client
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

# (environment variable with the space id, agent name, what it answers) - the env vars are bound to the app's
# genie-consumer / genie-finance / genie-manufacturing resources (app.yaml, notebooks/06_router_app.py)
DOMAIN_AGENTS = [
    ("GENIE_SPACE_CONSUMER", "Consumer Analyst",
     "webshop (DTC) GMV, net sales, orders, AOV and returns by market, brand and product; shoppers and CLTV "
     "segments; Fjällmark Friends loyalty tiers; subscriptions; GDPR consents"),
    ("GENIE_SPACE_FINANCE", "Finance Analyst",
     "the OFFICIAL Net Revenue, COGS and gross margin (general ledger, EUR) by entity, brand and channel; "
     "production variances; receivables, overdue AR and DSO; payables; cost estimates"),
    ("GENIE_SPACE_MANUFACTURING", "Manufacturing Analyst",
     "plants and production lines: OEE, yield, scrap, downtime, on-time completion, late orders, yield loss "
     "reasons, batches, equipment, production cost variance"),
]

ROUTER_INSTRUCTIONS = """You are the Fjällmark router: the single entry point to the data of Fjällmark Consumer Goods AB, a
fictional Nordic consumer-goods group (brands Björkö Pantry, Kallkälla, Mjuk Care; company codes SE01, NO01,
DK01, FI01, DE01, PL01; group currency EUR; data 2024-01 to 2026-09, September 2026 is the last closed month).

You never query data yourself. Three Genie Agents do, each curated on its own governed domain:
{agents}

How you work:
1. Decide which analyst(s) own the question. "Revenue", "sales", "turnover" mean the Finance Analyst's official
   Net Revenue unless the user explicitly asks about the webshop.
2. Ask each analyst a self-contained question with its query tool, in that analyst's vocabulary: name the
   period, the entity or market and the currency you need. Split a question that needs two domains into one
   question per analyst and ask them independently.
3. A query tool may return before the answer is ready (a status plus conversation_id and message_id): then call
   the matching poll tool of the same analyst until the answer is complete.
4. Combine answers like with like. Never add or compare amounts of different currencies or definitions; when
   you compare (e.g. webshop net sales vs the DTC net revenue finance books), make sure both are the same
   currency and period, and explain the difference with the definitions (VAT, shipping, discounts, returns,
   cancellations) and known business events the analysts mention.
5. Use only numbers the analysts returned. Simple arithmetic on them (a difference, a share) is fine - show it.
6. Reply with the answer first, then a short "Sources" line: which analyst answered which part, with the
   definition, period and currency each used.
7. Every analyst answers under Unity Catalog governance (row filters by company code, masked personal data).
   Empty results or missing company codes can be governance working as designed - say so instead of guessing. Never ask for or reveal personal data about shoppers.
{unavailable}"""


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
    """The router agent with the domain agents that are reachable for the signed-in user."""
    configured = init_genie_servers(WorkspaceClient())   # the app's service principal
    healthy, unavailable = await connect_healthy_mcp_servers(stack, [s for s, *_ in configured])
    available = {getattr(s, "name", "") for s in healthy}
    agents = "\n".join(
        f"- {name} (tools query_space_{space_id} and poll_response_{space_id}): {scope}"
        for _, name, scope, space_id in configured if name in available) or "- (none reachable)"
    missing = [name for _, name, _ in DOMAIN_AGENTS if name not in available]
    note = (f"8. Not available right now: {', '.join(missing)}. Say so when a question needs it, "
            "and answer the rest.") if missing else ""
    return Agent(
        name="Fjällmark router",
        instructions=ROUTER_INSTRUCTIONS.format(agents=agents, unavailable=note),
        model=LLM_ENDPOINT,
        model_settings=MODEL_SETTINGS,
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
        # The router runs inside an AsyncExitStack so the Genie MCP servers stay open for the whole request.
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
