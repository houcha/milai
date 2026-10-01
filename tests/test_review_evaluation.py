"""Validate live comparison fixtures and labels before making paid requests."""

import pytest

from milai.review_evaluation import cases, check, fixture
from milai.reviewer import ReviewOutput, review_input
from milai.store import Store


@pytest.mark.parametrize("case", cases(), ids=lambda case: case.name)
def test_comparison_labels_satisfy_storage_and_reject_wrong_score(tmp_path, case):
    store = Store(tmp_path / "comparison.db")
    try:
        ctx = fixture(store, case)
        data = review_input(ctx)
        assessment = {
            "exercise_id": ctx.selected_exercise_id,
            "feedback": "",
            "score": None
            if case.content
            else {
                "correct": sum(case.correct),
                "total": case.legacy_total or len(case.correct),
            },
            "item_results": [
                {
                    "item_number": i,
                    "correct": correct,
                    "feedback": "" if correct else "Use the requested form.",
                }
                for i, correct in enumerate(case.correct, 1)
            ]
            if case.content
            else [],
            "blank_results": [
                {
                    "blank_number": i,
                    "correct": correct,
                    "feedback": "" if correct else "Use the requested form.",
                }
                for i, correct in enumerate(case.correct, 1)
            ]
            if "{{blank}}" in case.task
            else [],
            "observations": [
                {
                    "skill_id": data["skills"][0]["id"],
                    "outcome": case.outcome,
                    "issue_severity": case.severity,
                    "rationale": "Labelled synthetic evidence.",
                }
            ],
        }
        output = ReviewOutput.model_validate(
            {
                "assessment": assessment,
                "reply": "Reviewed.",
                "summary": "Updated summary.",
                "completion_summary": "Regular past forms understood; one local slip."
                if case.complete_set
                else None,
            }
        )
        baseline = list(store.db.iterdump())
        assert check(case, ctx, output) == []
        assert list(store.db.iterdump()) == baseline
        assert review_input(ctx) == data
        assert (data["completion_context"] is not None) is case.complete_set
        if case.content:
            output.assessment.item_results[0].correct = not case.correct[0]
            output.assessment.item_results[0].feedback = (
                "" if not case.correct[0] else "Use the requested form."
            )
        else:
            assert output.assessment.score is not None
            output.assessment.score.correct = 0
        assert check(case, ctx, output)
        assert list(store.db.iterdump()) == baseline
    finally:
        store.close()
