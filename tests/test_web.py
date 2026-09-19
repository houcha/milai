from milai.web import learning_view


def test_learning_view_projects_curriculum_focus_and_skill_evidence():
    snapshot = {
        "profile": {
            "target_language": {"value": "German", "learner_quote": "private"},
            "goals": {"value": "Prepare for work in Berlin"},
        },
        "curriculum": [
            {
                "id": "curriculum-1",
                "title": "German for Berlin",
                "outline": ["Accusative articles", "Past events"],
            }
        ],
        "exercises": [
            {
                "id": "exercise-1",
                "skill": "German accusative indefinite articles",
                "task": "Ask for a table using einen.",
            }
        ],
        "evidence": [
            {
                "skill": "German accusative indefinite articles",
                "outcome": "needs_work",
                "independent_success": False,
            },
            {
                "skill": "German accusative indefinite articles",
                "outcome": "success",
                "independent_success": False,
            },
            {
                "skill": "German accusative indefinite articles",
                "outcome": "success",
                "independent_success": True,
            },
        ],
    }

    view = learning_view(snapshot)

    assert view["profile"] == {
        "target_language": "German",
        "goals": "Prepare for work in Berlin",
    }
    assert view["curriculum"]["id"] == "curriculum-1"
    assert view["current_focus"]["id"] == "exercise-1"
    assert view["current_lesson"] is None
    assert view["skills"] == [
        {
            "name": "German accusative indefinite articles",
            "attempts": 3,
            "independent_successes": 1,
            "assisted_successes": 1,
            "needs_work": 1,
            "last_outcome": "success",
            "exercises": 1,
        }
    ]
