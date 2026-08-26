"""API tests for the structured assessment workflow."""

import pytest


def _complete_answers(questions: list[dict[str, object]]) -> list[dict[str, str]]:
    """Build a valid answer sheet using one deterministic option per question."""
    return [
        {"question_id": str(question["id"]), "answer": "B"}
        for question in questions
    ]


@pytest.mark.asyncio
async def test_submit_report_and_history(app_client) -> None:
    """A complete answer sheet produces a persisted structured report."""
    questions_response = await app_client.get("/api/assessments/questions")
    assert questions_response.status_code == 200
    questions = questions_response.json()["questions"]
    assert len(questions) == 10

    payload = {"session_id": "structured-test", "answers": _complete_answers(questions)}
    submission = await app_client.post("/api/assessments", json=payload)
    assert submission.status_code == 200
    created = submission.json()
    assert created["report"]["overall_score"] == 50
    assert created["report"]["level"] == "入门"
    assert len(created["report"]["dimensions"]) == 4

    detail = await app_client.get(f"/api/assessments/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["answers"]["programming_level"] == "B"

    history = await app_client.get("/api/assessments/history/structured-test")
    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_rejects_incomplete_answers(app_client) -> None:
    """The API refuses a submission that omits any fixed question."""
    questions = (await app_client.get("/api/assessments/questions")).json()["questions"]
    payload = {"session_id": "incomplete-test", "answers": _complete_answers(questions)[:-1]}

    response = await app_client.post("/api/assessments", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_and_clear_history(app_client) -> None:
    """A report can be deleted individually and remaining history can be cleared."""
    questions = (await app_client.get("/api/assessments/questions")).json()["questions"]
    payload = {"session_id": "history-test", "answers": _complete_answers(questions)}
    first = (await app_client.post("/api/assessments", json=payload)).json()
    second = (await app_client.post("/api/assessments", json=payload)).json()

    deleted = await app_client.delete(
        f"/api/assessments/{first['id']}", params={"session_id": "history-test"}
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    cleared = await app_client.delete("/api/assessments/history/history-test")
    assert cleared.status_code == 200
    assert cleared.json() == {"deleted": 1}

    detail = await app_client.get(f"/api/assessments/{second['id']}")
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_assessment_pages_render(app_client) -> None:
    """Each PRD assessment route renders the shared page shell."""
    for path in ("/assessment", "/assessment/quiz", "/assessment/loading", "/assessment/report/demo", "/assessment/history"):
        response = await app_client.get(path)
        assert response.status_code == 200
        assert 'id="assessment-root"' in response.text
