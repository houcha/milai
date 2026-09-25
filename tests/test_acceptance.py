"""Keep the synthetic learner's answer aligned with the selected task."""

import pytest

from milai.acceptance import choose_trip_exercise, trip_answer_for


def test_synthetic_answer_selects_open_trip_writing_task():
    fill_blanks = {
        "id": "fill",
        "task": "Complete six blanks with past verbs in parentheses.",
        "scaffolding": "none",
    }
    trip = {
        "id": "trip",
        "task": "Write six sentences about a completed trip using regular past verbs.",
        "scaffolding": "none",
    }
    assert choose_trip_exercise([fill_blanks, trip])["id"] == "trip"
    with pytest.raises(RuntimeError, match="compatible"):
        choose_trip_exercise([fill_blanks])


def test_synthetic_answer_meets_generated_sentence_and_verb_contract():
    mixed = {
        "task": "Write four affirmative sentences about a day trip. "
        "Use two regular and two irregular verbs, with a past-time phrase in each."
    }
    answer = trip_answer_for(mixed)
    assert answer.count(".") == 4
    assert "went" in answer and "visited" in answer
    assert "Last Saturday" in answer and "Later that night" in answer

    regular = {
        "task": "Write 5–7 sentences about a trip using six different regular verbs."
    }
    answer = trip_answer_for(regular)
    assert answer.count(".") == 6
    assert "went" not in answer
    assert "organized" in answer
