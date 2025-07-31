import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from httpx import delete
from llama_stack.distribution.library_client import (
    AsyncLlamaStackAsLibraryClient,
    LlamaStackAsLibraryClient,
)
from llama_stack_client import AsyncLlamaStackClient, LlamaStackClient

from llama_stack_client.lib.agents.agent import AsyncAgent
from llama_stack_client.types.shared_params.agent_config import AgentConfig

import yaml
from loguru import logger
from .config import load_config_from_template
from .tools import promtools
from persai.errors import ConfigurationError


@contextmanager
def config_file():
    """Context manager for llamastack configuration, preferring template over static."""
    base_dir = Path(__file__).parent
    template_path = base_dir / "llamastack.yaml.j2"
    static_path = base_dir / "llamastack.yaml"

    if template_path.exists():
        # Render template to temporary file
        config_data = load_config_from_template(template_path)

        # Validate that we have at least one model configured
        models = config_data.get("models", [])
        if not models:
            logger.warning(
                "No models configured in template (no API keys set?), falling back to static config"
            )
            yield str(static_path.absolute())
            return

        # Create temporary file in the same directory
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=True, dir=base_dir
        ) as tmp:
            yaml.dump(config_data, tmp)
            temp_file = tmp.name
            logger.info(
                "Using templated config",
                model_count=len(models),
                models=[m["model_id"] for m in models],
            )
            yield temp_file
            return

    yield str(static_path.absolute())


async def get_async_llama_stack_client() -> AsyncLlamaStackClient:
    """Retrieve Async Llama stack client according to configuration."""
    with config_file() as config_path:
        logger.info("Initializing LlamaStack client", config_path=config_path)
        client = AsyncLlamaStackAsLibraryClient(config_path)
        await client.initialize()
        logger.info("LlamaStack client initialized successfully")
        return client


def get_llama_stack_client() -> LlamaStackClient:
    """Retrieve Async Llama stack client according to configuration."""
    with config_file() as config_path:
        client = LlamaStackAsLibraryClient(config_path)
        client.initialize()
        return client


SYSTEM_PROMPT = os.environ.get(
    "PERSAI_SYSTEM_PROMPT",
    """\
You are a Prometheus expert, answering questions about Kubernetes and OpenShift cluster questions.

Make sure to use the available tools to get the list of available metrics.
DON'T USE metrics not received from the tools first.

ALERTS use "alertstate" label to indicate the firing state.

Try to use the metrics also to answer questions about the Kubernetes, if possible with the metrics.

Don't describe raw outputs of the time-series data. Provide only a human-readable summary.
""",
)


def get_default_model(config_data):
    """Get default model from env or first available in config."""
    if env_model := os.environ.get("PERSAI_DEFAULT_MODEL"):
        return env_model

    # Get first available model from config
    models = config_data.get("models", [])
    if models:
        return models[0]["model_id"]

    # Fallback
    return "gpt-4o-mini"


async def initialize_agent(client: AsyncLlamaStackClient):
    # Load config to get available models
    with config_file() as config_path:
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        model = get_default_model(config_data)
        logger.info("Initializing agent", model=model)

        # Validate model exists in config
        available_models = {m["model_id"] for m in config_data.get("models", [])}
        if model not in available_models:
            logger.error(
                "Model not available",
                requested_model=model,
                available_models=list(available_models),
            )
            raise ConfigurationError(
                f"Model {model} not available. Available: {available_models}"
            )

    # TODO: consider improving llamastack to allow searching and updating existing agents.
    # For now, just delete old agents on startup and define a new one. The downside is
    # we loose the sessions every time we restart the server. Acceptable for now, but needs to be
    # revisited once going for production.
    existing_agents = (await client.agents.list()).data
    if existing_agents:
        logger.info("Cleaning up existing agents", agent_count=len(existing_agents))
        for a in existing_agents:
            await client.agents.delete(agent_id=a["agent_id"])

    agent_config = AgentConfig(name="persai", model=model, instructions=SYSTEM_PROMPT)

    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=agent_config["model"],
        instructions=agent_config["instructions"],
        tools=promtools,
    )

    # TODO: fix llama_stack_client to be able to pass agent name in the args.
    agent.agent_config["name"] = agent_config["name"]
    await agent.initialize()
    logger.info("Agent initialized successfully", agent_id=agent.agent_id, model=model)
    return agent


# Global variables to store initialized clients
_async_client: AsyncLlamaStackClient | None = None
_agent: AsyncAgent | None = None


async def get_async_client() -> AsyncLlamaStackClient:
    global _async_client
    if _async_client is None:
        _async_client = await get_async_llama_stack_client()
    return _async_client


async def get_agent() -> AsyncAgent:
    global _agent
    if _agent is None:
        client = await get_async_client()
        _agent = await initialize_agent(client)
    return _agent


async def initialize() -> None:
    """Initialize the LlamaStack client and agent at startup.

    This function should be called during server startup to ensure
    configuration errors are caught immediately.
    """
    await get_async_client()
    await get_agent()
