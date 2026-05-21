"""Scripted fakes for adaptive agent tests."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentCall:
    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


type ScriptedAgentResponse = object | Exception


class ScriptedAdaptiveAgent:
    def __init__(self, responses: Iterable[ScriptedAgentResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[AgentCall] = []

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("run", *args, **kwargs)

    async def decide(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("decide", *args, **kwargs)

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("generate", *args, **kwargs)

    def _next(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(AgentCall(method=method, args=args, kwargs=kwargs))
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return result


class ScriptedAssessmentInterviewer(ScriptedAdaptiveAgent):
    async def start_assessment(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("start_assessment", *args, **kwargs)

    async def continue_assessment(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("continue_assessment", *args, **kwargs)

    async def evaluate_answer(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("evaluate_answer", *args, **kwargs)

    async def next_turn(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("next_turn", *args, **kwargs)


class ScriptedCurriculumDesigner(ScriptedAdaptiveAgent):
    async def draft_curriculum(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("draft_curriculum", *args, **kwargs)

    async def revise_curriculum(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("revise_curriculum", *args, **kwargs)


class ScriptedLessonTutor(ScriptedAdaptiveAgent):
    async def generate_lesson_content(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("generate_lesson_content", *args, **kwargs)

    async def generate_exercises(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("generate_exercises", *args, **kwargs)

    async def change_lesson(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("change_lesson", *args, **kwargs)

    async def respond_to_theory_request(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("respond_to_theory_request", *args, **kwargs)

    async def evaluate_answer(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("evaluate_answer", *args, **kwargs)

    async def give_hint(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("give_hint", *args, **kwargs)

    async def adapt_practice(self, *args: Any, **kwargs: Any) -> Any:
        return self._next("adapt_practice", *args, **kwargs)
