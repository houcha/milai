"""Concrete adaptive agent exports."""

from importlib import import_module
from typing import Any

__all__ = [
    "AssessmentInterviewer",
    "CurriculumDesigner",
    "LessonTutor",
]

_AGENT_MODULES = {
    "AssessmentInterviewer": "milai.agents.assessment",
    "CurriculumDesigner": "milai.agents.curriculum",
    "LessonTutor": "milai.agents.lesson",
}


def __getattr__(name: str) -> Any:
    if module_name := _AGENT_MODULES.get(name):
        module = import_module(module_name)
        return getattr(module, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
