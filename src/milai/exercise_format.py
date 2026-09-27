"""The small, declarative extension used for interactive exercise Markdown."""

BLANK_MARKER = "{{blank}}"
MAX_EXERCISE_BLANKS = 12
EXERCISE_TASK_DESCRIPTION = (
    "Complete task as Markdown, with each numbered item on its own line. "
    "Each top-level numbered item gets its own answer area; "
    "use prose or bullets for instructions. "
    "For short fill-in answers, place {{blank}} at each input location (up to 12). "
    "Use plain prose markers, never HTML or markers inside code, math, or links. "
    "Omit markers for open-ended writing; do not include answers."
)


def validate_exercise_task(task: str) -> str:
    if task.count(BLANK_MARKER) > MAX_EXERCISE_BLANKS:
        raise ValueError("An exercise can have at most 12 inline blanks")
    if "{{blank" in task.replace(BLANK_MARKER, ""):
        raise ValueError("Use exactly {{blank}} for each inline answer field")
    return task


def terminal_exercise_task(task: str) -> str:
    """Show numbered blanks without exposing renderer markers in terminal chat."""
    pieces = task.split(BLANK_MARKER)
    return pieces[0] + "".join(
        f"___ [blank {index}]" + piece
        for index, piece in enumerate(pieces[1:], start=1)
    )
