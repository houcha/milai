"""Configuration loading for milai."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_STORAGE_PATH = Path.home() / ".milai" / "state.json"


class LLMConfig(BaseModel):
    model: str = "gemini/gemma-4-31b-it"
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 1024


class LLMProfilesConfig(BaseModel):
    default_profile: str = "light"
    profiles: dict[str, LLMConfig] = Field(
        default_factory=lambda: {"light": LLMConfig()}
    )

    @model_validator(mode="after")
    def validate_default_profile(self) -> "LLMProfilesConfig":
        if self.default_profile not in self.profiles:
            raise ValueError(f"missing LLM profile: {self.default_profile}")
        return self


class StateConfig(BaseModel):
    llm: str | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    llm: LLMProfilesConfig = Field(default_factory=LLMProfilesConfig)
    states: dict[str, StateConfig] = Field(default_factory=dict)
    storage_path: Path = DEFAULT_STORAGE_PATH

    @model_validator(mode="before")
    @classmethod
    def normalize_storage(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        storage = data.get("storage")
        if isinstance(storage, dict) and "path" in storage:
            data = dict(data)
            data["storage_path"] = storage["path"]
        return data

    @model_validator(mode="after")
    def validate_state_routes(self) -> "Config":
        for state_name, state in self.states.items():
            if state.llm is not None and state.llm not in self.llm.profiles:
                msg = (
                    f"state {state_name!r} references missing LLM profile {state.llm!r}"
                )
                raise ValueError(msg)
        return self


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _default_config_data() -> dict[str, Any]:
    return Config().model_dump(mode="json")


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raw = {}
    return Config.model_validate(_merge_config(_default_config_data(), raw))
