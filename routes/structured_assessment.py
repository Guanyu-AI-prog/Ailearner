"""Structured assessment API and page routes."""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agent.schemas import StructuredAssessmentRequest
from config.assessment import ASSESSMENT_QUESTIONS
from db import (
    clear_structured_assessments,
    create_structured_assessment,
    delete_structured_assessment,
    get_structured_assessment,
    list_structured_assessments,
)
import asyncio

from services.assessment_service import generate_assessment_report
from services.report_enricher import enrich_report
from db import update_structured_assessment_report


logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api/assessments", tags=["structured-assessments"])
page_router = APIRouter(tags=["structured-assessment-pages"])
templates = Jinja2Templates(directory="web/templates")


def _validated_answers(payload: StructuredAssessmentRequest) -> dict[str, str]:
    """Validate that a submission covers the complete fixed question bank."""
    answers = {item.question_id: item.answer for item in payload.answers}
    expected_ids = {question["id"] for question in ASSESSMENT_QUESTIONS}
    if len(answers) != len(payload.answers) or set(answers) != expected_ids:
        raise HTTPException(
            status_code=422,
            detail="Answers must contain each structured assessment question exactly once.",
        )
    return answers


def _render_page(request: Request, page: str, assessment_id: str = "") -> HTMLResponse:
    """Render the shared assessment shell for a specific workflow page."""
    return templates.TemplateResponse(
        request,
        "assessment.html",
        {"page": page, "assessment_id": assessment_id},
    )


@page_router.get("/assessment", response_class=HTMLResponse)
async def assessment_entry(request: Request) -> HTMLResponse:
    """Render the structured assessment entry page."""
    return _render_page(request, "entry")


@page_router.get("/assessment/quiz", response_class=HTMLResponse)
async def assessment_quiz(request: Request) -> HTMLResponse:
    """Render the paginated quiz page."""
    return _render_page(request, "quiz")


@page_router.get("/assessment/loading", response_class=HTMLResponse)
async def assessment_loading(request: Request) -> HTMLResponse:
    """Render the assessment submission loading page."""
    return _render_page(request, "loading")


@page_router.get("/assessment/report/{assessment_id}", response_class=HTMLResponse)
async def assessment_report(request: Request, assessment_id: str) -> HTMLResponse:
    """Render an assessment report page."""
    return _render_page(request, "report", assessment_id)


@page_router.get("/assessment/history", response_class=HTMLResponse)
async def assessment_history(request: Request) -> HTMLResponse:
    """Render the structured assessment history page."""
    return _render_page(request, "history")


@api_router.get("/questions")
async def list_questions() -> dict[str, object]:
    """Return the fixed structured assessment question bank."""
    return {"questions": ASSESSMENT_QUESTIONS}


@api_router.post("")
async def submit_assessment(payload: StructuredAssessmentRequest) -> dict[str, object]:
    """Generate and persist a report for one complete answer sheet."""
    answers = _validated_answers(payload)
    report = generate_assessment_report(answers)
    assessment_id = str(uuid4())
    await create_structured_assessment(assessment_id, payload.session_id, answers, report)

    async def _run_enrichment() -> None:
        enriched, source = await enrich_report(report, answers)
        if source == "enriched":
            await update_structured_assessment_report(assessment_id, enriched)
            logger.info("测评报告已个人化改写 %s", assessment_id)
        else:
            logger.info("测评报告保持模板版 %s", assessment_id)

    asyncio.create_task(_run_enrichment())
    return {"id": assessment_id, "report": report}


@api_router.get("/history/{session_id}")
async def assessment_history_data(session_id: str) -> dict[str, object]:
    """Return a session's historical assessment summaries."""
    return {"items": await list_structured_assessments(session_id)}


@api_router.delete("/history/{session_id}")
async def clear_assessment_history(session_id: str) -> dict[str, int]:
    """Delete every structured assessment for a session."""
    deleted = await clear_structured_assessments(session_id)
    return {"deleted": deleted}


@api_router.get("/{assessment_id}")
async def assessment_detail(assessment_id: str) -> dict[str, object]:
    """Return one persisted assessment report."""
    assessment = await get_structured_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    return assessment


@api_router.delete("/{assessment_id}")
async def delete_assessment(assessment_id: str, session_id: str) -> dict[str, bool]:
    """Delete one report after confirming the owning browser session."""
    assessment = await get_structured_assessment(assessment_id)
    if assessment is None or assessment["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    return {"deleted": await delete_structured_assessment(assessment_id)}
