"""Package-backed prompt asset rendering."""

from importlib import resources
from typing import Any

from jinja2 import StrictUndefined, Template


def render_prompt_template(path: str, variables: dict[str, Any]) -> str:
    """Render a packaged Jinja2 text prompt template."""
    asset = resources.files("milai.llm.prompts").joinpath(path)
    template = asset.read_text(encoding="utf-8")
    return Template(template, undefined=StrictUndefined).render(**variables)
