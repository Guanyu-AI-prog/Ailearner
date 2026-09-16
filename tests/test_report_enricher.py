"""报告个人化改写层测试：兜底三防线 + 正常路径 + 异步落库。"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from services.report_enricher import enrich_report
from services.assessment_service import generate_assessment_report
from config.assessment import ASSESSMENT_QUESTIONS


def _full_answers() -> dict[str, str]:
    return {q["id"]: chr(ord("A") + i % 4) for i, q in enumerate(ASSESSMENT_QUESTIONS)}


def _call_enrich(report, answers, llm_text, api_key="sk-test"):
    """统一入口：patch 掉 LLM 调用与 key 配置。"""
    async def fake_call(messages):
        return llm_text

    with patch("services.report_enricher.config") as mock_config:
        mock_config.LLM_API_KEY = api_key
        with patch("services.report_enricher._call_llm", new=fake_call):
            return asyncio.run(enrich_report(report, answers))


def test_no_key_falls_back_to_template():
    report = generate_assessment_report(_full_answers())
    async def fake_call(messages):
        raise AssertionError("无 key 不应发起请求")
    with patch("services.report_enricher.config") as mock_config:
        mock_config.LLM_API_KEY = ""
        from unittest.mock import patch as _p
        with _p("services.report_enricher._call_llm", new=fake_call):
            result, source = asyncio.run(enrich_report(report, _full_answers()))
    assert source == "template"
    assert result == report


def test_tampered_score_is_rejected():
    report = generate_assessment_report(_full_answers())
    tampered = dict(report)
    tampered["overall_score"] = 999
    result, source = _call_enrich(report, _full_answers(), json.dumps(tampered, ensure_ascii=False))
    assert source == "template"
    assert result == report


def test_extra_top_key_rejected():
    report = generate_assessment_report(_full_answers())
    candidate = dict(report)
    candidate["score_hint"] = "借机作弊"
    result, source = _call_enrich(report, _full_answers(), json.dumps(candidate, ensure_ascii=False))
    assert source == "template"


def test_invalid_json_rejected():
    report = generate_assessment_report(_full_answers())
    result, source = _call_enrich(report, _full_answers(), "这不是JSON")
    assert source == "template"
    assert result == report


def test_valid_enrichment_passes():
    report = generate_assessment_report(_full_answers())
    enriched = json.loads(json.dumps(report, ensure_ascii=False))
    enriched["positioning"] = "你提到每天只有30分钟，先把刷题节奏砍到最小可坚持。"
    for dim in enriched["dimensions"]:
        dim["analysis"] = "结合你的答卷情况，这一个维度就是你启动时最先踩的坑。"
    result, source = _call_enrich(report, _full_answers(), json.dumps(enriched, ensure_ascii=False))
    assert source == "enriched"
    assert result["overall_score"] == report["overall_score"]
    assert result["level"] == report["level"]
    assert result["profile"] == report["profile"]
    assert "30分钟" in result["positioning"]


def test_new_number_in_list_rejected():
    """改写不允许出现报告里没有的新数字（量化承诺）。"""
    report = generate_assessment_report(_full_answers())
    candidate = json.loads(json.dumps(report, ensure_ascii=False))
    original_digits = set("".join(json.dumps(report, ensure_ascii=False).split()))
    candidate["pitfalls"][0] = "预计 777 天学会 Python，别急。"
    result, source = _call_enrich(report, _full_answers(), json.dumps(candidate, ensure_ascii=False))
    assert source == "template"


def test_llm_failure_falls_back():
    report = generate_assessment_report(_full_answers())
    async def boom(messages):
        raise TimeoutError("LLM 挂了")
    with patch("services.report_enricher.config") as mock_config:
        mock_config.LLM_API_KEY = "sk-test"
        with patch("services.report_enricher._call_llm", new=boom):
            result, source = asyncio.run(enrich_report(report, _full_answers()))
    assert source == "template"
    assert result is report
