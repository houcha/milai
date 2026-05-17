import pytest
from pydantic import ValidationError


def test_missing_config_file_raises_file_not_found(tmp_path) -> None:
    from milai.config import load_config

    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_config_merges_profile_overrides_and_state_routing(tmp_path) -> None:
    from milai.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text(
        """
llm:
  default_profile: light
  profiles:
    light:
      model: openai/gpt-4o-mini
    heavy:
      model: anthropic/claude-haiku-4-5
      temperature: 0.2
states:
  deviation:
    llm: heavy
"""
    )

    config = load_config(path)

    assert config.llm.default_profile == "light"
    assert config.llm.profiles["light"].model == "openai/gpt-4o-mini"
    assert config.llm.profiles["light"].max_tokens == 1024
    assert config.llm.profiles["light"].reasoning_effort == "none"
    assert config.llm.profiles["heavy"].temperature == 0.2
    assert config.states["deviation"].llm == "heavy"


def test_config_loads_reasoning_effort_override(tmp_path) -> None:
    from milai.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text(
        """
llm:
  profiles:
    light:
      reasoning_effort: minimal
"""
    )

    config = load_config(path)

    assert config.llm.profiles["light"].reasoning_effort == "minimal"


def test_config_rejects_state_routes_to_unknown_llm_profiles(tmp_path) -> None:
    from milai.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text(
        """
states:
  deviation:
    llm: missing
"""
    )

    with pytest.raises(ValidationError, match="missing"):
        load_config(path)
