"""Console entrypoint for milai."""

import argparse
import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

from milai.config import Config, load_config
from milai.io.mediator import IOMediator
from milai.io.tui.app import TuiMediator
from milai.io.types import Choice
from milai.llm.client import LLMClient
from milai.llm.lesson_service import LessonLLM
from milai.llm.litellm_client import LiteLLMClient
from milai.models.state import PersistedState
from milai.models.user_state import UserState
from milai.state.handlers.assessment import AssessmentHandler
from milai.state.handlers.assessment_review import AssessmentReviewHandler
from milai.state.handlers.curriculum_complete import CurriculumCompleteHandler
from milai.state.handlers.curriculum_gen import CurriculumGenerationHandler
from milai.state.handlers.curriculum_review import CurriculumReviewHandler
from milai.state.handlers.deviation import DeviationHandler
from milai.state.handlers.lesson import LessonHandler
from milai.state.handlers.lesson_complete import LessonCompleteHandler
from milai.state.handlers.lesson_practice import LessonPracticeHandler
from milai.state.handlers.onboarding import OnboardingHandler
from milai.state.machine import HandlerMap, StateMachine
from milai.state.variants import (
    AssessmentReviewState,
    AssessmentState,
    CurriculumCompleteState,
    CurriculumGenerationState,
    CurriculumReviewState,
    DeviationState,
    LessonCompleteState,
    LessonPracticeState,
    LessonState,
    OnboardingState,
)
from milai.storage.client import StorageClient
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

    await prepare_launch_snapshot(storage, mediator)

    clients = {
        name: LiteLLMClient(profile) for name, profile in config.llm.profiles.items()
    }
    machine = StateMachine(
        storage=storage,
        handlers=build_handler_map(config=config, mediator=mediator, clients=clients),
    )
    await machine.run()


async def prepare_launch_snapshot(
    storage: StorageClient, mediator: IOMediator
) -> PersistedState:
    saved = await storage.load()
    if saved is None:
        return _fresh_snapshot()

    choice = await mediator.choose(
        "Saved session found",
        [
            Choice(
                label="Continue",
                value="continue",
                description="Resume the saved learning session",
            ),
            Choice(
                label="Start new",
                value="start_new",
                description="Replace the saved session",
            ),
        ],
    )
    if choice.value == "continue":
        return saved

    await storage.delete()
    fresh = _fresh_snapshot()
    await storage.save(fresh)
    return fresh


def build_handler_map(
    *,
    config: Config,
    mediator: IOMediator,
    clients: Mapping[str, LLMClient],
) -> HandlerMap:
    assessment_client = _client_for_state(
        config=config, clients=clients, state_name="assessment"
    )
    curriculum_generation_client = _client_for_state(
        config=config, clients=clients, state_name="curriculum_gen"
    )
    curriculum_review_client = _client_for_state(
        config=config, clients=clients, state_name="curriculum_review"
    )
    lesson_client = _client_for_state(
        config=config, clients=clients, state_name="lesson"
    )
    deviation_client = _client_for_state(
        config=config, clients=clients, state_name="deviation"
    )
    curriculum_complete_client = _client_for_state(
        config=config, clients=clients, state_name="curriculum_complete"
    )
    return {
        OnboardingState: OnboardingHandler(mediator),
        AssessmentState: AssessmentHandler(mediator, assessment_client),
        AssessmentReviewState: AssessmentReviewHandler(mediator),
        CurriculumGenerationState: CurriculumGenerationHandler(
            mediator,
            curriculum_generation_client,
        ),
        CurriculumReviewState: CurriculumReviewHandler(
            mediator,
            curriculum_review_client,
        ),
        LessonState: LessonHandler(mediator, LessonLLM(lesson_client)),
        LessonPracticeState: LessonPracticeHandler(mediator, LessonLLM(lesson_client)),
        DeviationState: DeviationHandler(mediator, deviation_client),
        LessonCompleteState: LessonCompleteHandler(mediator),
        CurriculumCompleteState: CurriculumCompleteHandler(
            mediator,
            curriculum_complete_client,
        ),
    }


def _client_for_state(
    *, config: Config, clients: Mapping[str, LLMClient], state_name: str
) -> LLMClient:
    state_profile = config.states.get(state_name)
    profile_name = (
        state_profile.llm
        if state_profile is not None and state_profile.llm is not None
        else config.llm.default_profile
    )
    return clients[profile_name]


def _fresh_snapshot() -> PersistedState:
    return PersistedState(user=UserState(), app=OnboardingState())


def main() -> None:
    """Run the milai application."""
    asyncio.run(run())
