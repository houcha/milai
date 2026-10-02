"""Strict pronunciation annotations; positions are Unicode code-point offsets."""

import re
from copy import deepcopy
from uuid import uuid4

ANNOTATION = re.compile(r"\[\[([a-z]{2,3}(?:-[A-Za-z0-9]{2,8})+)\|([^\[\]\r\n]+)\]\]")


def parse_spans(source: str) -> tuple[str, list[dict]]:
    """Remove annotations and preserve exact text, punctuation and offsets."""
    parts: list[str] = []
    spans: list[dict] = []
    cursor = position = 0
    for match in ANNOTATION.finditer(source):
        prefix = source[cursor : match.start()]
        if "[[" in prefix or "]]" in prefix:
            raise ValueError("Malformed or nested pronunciation annotation")
        locale, text = match.groups()
        if (
            not text.strip()
            or len(text) > 4096
            or any(char in text for char in "*_`{}<>|\\")
        ):
            raise ValueError("Pronunciation spans require plain text without blanks")
        position += len(prefix)
        parts.extend((prefix, text))
        spans.append(
            {"id": uuid4().hex, "position": position, "text": text, "locale": locale}
        )
        position += len(text)
        cursor = match.end()
    tail = source[cursor:]
    if "[[" in tail or "]]" in tail:
        raise ValueError("Malformed or nested pronunciation annotation")
    parts.append(tail)
    return "".join(parts), spans


def extract_fields(value: dict, fields: list[str]) -> tuple[dict, list[dict]]:
    """Copy content, cleaning only the explicitly public content fields."""
    clean = deepcopy(value)
    spans = []
    for field in fields:
        path = field.split(".")
        parent = clean
        for key in path[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent[key]
        key = path[-1]
        parent[key], found = parse_spans(parent[key])
        spans.extend({**span, "field": field} for span in found)
    return clean, spans


def document_fields(document: dict) -> list[str]:
    return [
        "objective",
        "recap",
        *(
            f"{group}.{index}.{field}"
            for group in ("sections", "worked_examples")
            for index, _ in enumerate(document[group])
            for field in ("title", "markdown")
        ),
    ]
