"""Typed exercise content, application-owned instructions, and answer contracts."""

from __future__ import annotations

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from milai.exercise_format import BLANK_MARKER


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TextItem(ContentModel):
    text: str = Field(min_length=1, max_length=800)
    context: str = Field(
        max_length=300,
        description="Optional factual disambiguation; no instructions or answer hints.",
    )
    references: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Private reference answers; accept other valid answers too.",
    )

    @model_validator(mode="after")
    def bounded_references(self) -> Self:
        if any(not answer.strip() or len(answer) > 1000 for answer in self.references):
            raise ValueError("Reference answers must contain 1–1000 characters")
        return self


class ChoiceItem(ContentModel):
    text: str = Field(min_length=1, max_length=800)
    context: str = Field(max_length=300)
    options: list[str] = Field(min_length=2, max_length=5)
    correct_option: int = Field(
        ge=1, le=5, description="One-based correct option number."
    )

    @model_validator(mode="after")
    def valid_options(self) -> Self:
        if self.correct_option > len(self.options):
            raise ValueError("Correct option must refer to an available option")
        if len(set(self.options)) != len(self.options) or any(
            not option.strip() or len(option) > 200 for option in self.options
        ):
            raise ValueError(
                "Options must be distinct, nonempty, and at most 200 characters"
            )
        return self


class ChooseForm(ContentModel):
    type: Literal["choose_form"]
    items: list[ChoiceItem] = Field(min_length=1, max_length=12)


class CompleteSentence(ContentModel):
    type: Literal["complete_sentence"]
    items: list[TextItem] = Field(min_length=1, max_length=12)


class Translate(ContentModel):
    type: Literal["translate"]
    language: str | None = Field(
        max_length=80,
        pattern=r"^[^\r\n{}]+$",
        description="Answer language; null uses the lesson language.",
    )
    items: list[TextItem] = Field(min_length=1, max_length=12)


class Transform(ContentModel):
    type: Literal["transform"]
    target_form: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[^\r\n{}]+$",
        description="A short grammatical form label, not extra instructions.",
    )
    items: list[TextItem] = Field(min_length=1, max_length=12)


class ShortResponse(ContentModel):
    type: Literal["short_response"]
    language: str | None = Field(max_length=80, pattern=r"^[^\r\n{}]+$")
    response_scope: Literal["one sentence", "a short message"]
    focus: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[^\r\n{}]+$",
        description="One visible language focus; assess it holistically.",
    )
    items: list[TextItem] = Field(min_length=1, max_length=12)


class ExerciseContract(ContentModel):
    version: Literal[1]
    content: ChooseForm | CompleteSentence | Translate | Transform | ShortResponse

    @model_validator(mode="after")
    def valid_content(self) -> Self:
        gapped = self.content.type in {"choose_form", "complete_sentence"}
        for item in self.content.items:
            if item.text.count(BLANK_MARKER) != int(gapped):
                raise ValueError(
                    "Choice and completion items need exactly one {{blank}}; "
                    "other types have none"
                )
            if "{{blank" in item.text.replace(BLANK_MARKER, ""):
                raise ValueError("Use exactly {{blank}} for the answer location")
        if isinstance(self.content, CompleteSentence) and any(
            len(answer) > 200 or "\n" in answer or "\r" in answer
            for item in self.content.items
            for answer in item.references
        ):
            raise ValueError(
                "Reference fills must fit a single-line 200-character blank"
            )
        if len(self.model_dump_json()) > 24000:
            raise ValueError("Exercise contract exceeds 24,000 characters")
        return self

    def resolved(self, language: str) -> ExerciseContract:
        content = self.content
        if isinstance(content, Translate | ShortResponse) and not content.language:
            content = content.model_copy(update={"language": language})
        return self.model_copy(update={"content": content})

    def public(self) -> dict:
        content = self.content
        match content:
            case ChooseForm():
                instruction = "Choose the correct form."
            case CompleteSentence():
                instruction = "Fill in the blank."
            case Translate():
                instruction = f"Translate into {content.language}."
            case Transform():
                instruction = f"Rewrite using {content.target_form}."
            case ShortResponse():
                instruction = (
                    f"Write {content.response_scope} in {content.language} "
                    f"using {content.focus}."
                )
        data = content.model_dump(exclude={"items"})
        return {
            "version": self.version,
            **data,
            "instruction": instruction,
            "items": [
                item.model_dump(exclude={"references", "correct_option"})
                for item in content.items
            ],
        }

    def task(self) -> str:
        public = self.public()
        lines = [public["instruction"], ""]
        for number, item in enumerate(public["items"], 1):
            lines.append(f"{number}. {item['text']}")
            if item["context"]:
                lines.append(f"   Context: {item['context']}")
            for option, text in enumerate(item.get("options", []), 1):
                lines.append(f"   Option {option}: {text}")
        task = "\n".join(lines)
        if len(task) > 12000:
            raise ValueError("Visible exercise content exceeds 12,000 characters")
        return task


class GeneratedExerciseContract(ExerciseContract):
    """Formats allowed for new exercises; saved contracts retain choice support."""

    content: CompleteSentence | Translate | Transform | ShortResponse


TITLES = {
    "choose_form": "Choose a form",
    "complete_sentence": "Complete a sentence",
    "translate": "Translate",
    "transform": "Transform a sentence",
    "short_response": "Write a short response",
}


def compile_exercise(exercise: dict, language: str) -> dict:
    contract = GeneratedExerciseContract.model_validate(exercise["contract"]).resolved(
        language
    )
    return {
        **exercise,
        "contract": contract.model_dump(),
        "title": TITLES[contract.content.type],
        "context": "",
        "task": contract.task(),
    }


def serialize_answers(values: list[str]) -> str:
    return "\n".join(
        f"Item {index}: {json.dumps(value, ensure_ascii=False)}"
        for index, value in enumerate(values, 1)
    )


def parse_answers(message: str, public: dict) -> list[str]:
    """Validate exact item mapping; permit ordinary text for a single item."""
    count = len(public["items"])
    if count == 1 and not message.startswith("Item 1:"):
        values = [message.strip()]
    else:
        lines = message.split("\n")
        values = []
        if len(lines) != count:
            raise ValueError(
                "Submit one JSON-quoted Item N answer per item; "
                "in the terminal use /answer <exercise-id> to answer interactively"
            )
        for index, line in enumerate(lines, 1):
            prefix = f"Item {index}: "
            if not line.startswith(prefix):
                raise ValueError("Answer labels must match the numbered items in order")
            try:
                value = json.loads(line[len(prefix) :])
            except ValueError as exc:
                raise ValueError(
                    "Each Item N answer must be a JSON-quoted string"
                ) from exc
            if not isinstance(value, str):
                raise ValueError("Each answer must be text")
            values.append(value.strip())
    for item, value in zip(public["items"], values, strict=True):
        if (
            public["type"] == "choose_form"
            and value
            and value not in {str(i) for i in range(1, len(item["options"]) + 1)}
        ):
            raise ValueError("Choose an available option number for each item")
        if public["type"] == "complete_sentence" and (
            len(value) > 200 or "\n" in value or "\r" in value
        ):
            raise ValueError("Each blank accepts a single line of up to 200 characters")
    return values
