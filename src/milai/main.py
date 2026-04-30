"""Console entrypoint for milai."""

import argparse
import asyncio
import logging
from pathlib import Path

from milai.config import Config, load_config
from milai.io.tui.app import TuiMediator
from milai.llm.litellm_client import LiteLLMClient
from milai.state.machine import StateMachine
from milai.storage.local import LocalStorage

logger = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path.home() / ".milai" / "config.yaml"


async def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="milai")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to config YAML file. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the saved session after confirmation before starting.",
    )
    args = parser.parse_args(argv)

    if args.config is not None and not args.config.exists():
        parser.error(f"config file does not exist: {args.config}")

    config_path = args.config or DEFAULT_CONFIG_PATH
    if config_path.exists():
        logger.info(f"Loading config from {config_path}")
        config = load_config(config_path)
    else:
        logger.info(f"Using default config because {config_path} does not exist")
        config = Config()

    storage = LocalStorage(config.storage_path)
    mediator = TuiMediator()

    if args.reset and await mediator.confirm(
        "Delete the saved session and start fresh?"
    ):
        await storage.delete()

    _clients = {
        name: LiteLLMClient(profile) for name, profile in config.llm.profiles.items()
    }
    machine = StateMachine(storage=storage, handlers={})
    await machine.run()


def main() -> None:
    """Run the milai application."""
    asyncio.run(run())
