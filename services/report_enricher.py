"""结构化测评报告的个人化改写层。

设计原则（改动四问留档 2026-09-16）：
- 分数与等级保持纯函数确定性（assessment_service.py 不动）
- 本模块只改写文本字段：positioning / dimensions[n].analysis / pitfalls / learning_path / short_term_plan
- 三道防线：key 缺失不出请求 / 10s 超时 / 结构校验（分数篡改即丢弃）
- 最差结果 = 模板版报告，不会比现状差
"""

import asyncio
import json
import logging
import re
from typing import Optional

from config import config
from services.enrichment_prompt import build_rewrite_prompt

logger = logging.getLogger(__name__)

ENRICH_TIMEOUT_SECONDS = 10

# 冻结字段：LLM 输出逐字相等的，否则整份丢弃
_FROZEN_FIELDS = {"overall_score", "level", "profile"}  # dimensions 的 id/score 在下方逐项校验

# 列表型可改写字段
_REWRITABLE_LIST_FIELDS = {"short_term_plan", "learning_path", "pitfalls"}

_MAX_ANALYSIS_LEN = 120
_MAX_POSITIONING_LEN = 60


def _digits_set(text: str) -> set:
    return set(re.findall(r"\d+", text))


def _llm_available() -> bool:
    return bool(config.LLM_API_KEY)


def _validate_enriched(original: dict, enriched_text: str, extra_allowed_digits: set = frozenset()) -> Optional[dict]:
    """校验 LLM 输出：结构一致 + 分数/等级/答案未被篡改，失败返回 None（丢弃）。"""
    try:
        candidate = json.loads(enriched_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("改写输出不是合法 JSON，丢弃")
        return None

    if not isinstance(candidate, dict):
        return None

    # 冻结字段逐字相等（防幻觉改分数）
    for field in _FROZEN_FIELDS:
        if candidate.get(field) != original.get(field):
            logger.warning("LLM 改写篡改了冻结字段 %s，丢弃", field)
            return None

    # 顶层 key 集合必须一致
    if set(candidate.keys()) != set(original.keys()):
        logger.warning("改写结果顶层字段集合不一致，丢弃")
        return None

    # positioning 长度上限
    if len(str(candidate.get("positioning", ""))) > _MAX_POSITIONING_LEN:
        return None

    # 每个 dimension：id/score 不可变，analysis 限长
    for orig_dim, new_dim in zip(original["dimensions"], candidate["dimensions"]):
        if new_dim.get("id") != orig_dim.get("id") or new_dim.get("score") != orig_dim.get("score"):
            logger.warning("分数维度被篡改，丢弃")
            return None
        if len(str(new_dim.get("analysis", ""))) > _MAX_ANALYSIS_LEN:
            return None

    # 数字防伪造：改写文本不允许出现原报告里没有的数字段
    orig_digits = set(re.findall(r"\d+", json.dumps(original, ensure_ascii=False))) | set(extra_allowed_digits)
    cand_digits = set(re.findall(r"\d+", json.dumps(candidate, ensure_ascii=False)))
    if cand_digits - orig_digits:
        logger.warning("改写引入新数字 %s，丢弃", cand_digits - orig_digits)
        return None

    # 列表字段：只允许字符串项，条数不增减
    for field in _REWRITABLE_LIST_FIELDS:
        orig_list = original.get(field, [])
        new_list = candidate.get(field)
        if not isinstance(new_list, list) or not all(isinstance(x, str) for x in new_list):
            return None
        if len(new_list) != len(orig_list):
            return None

    return candidate


async def enrich_report(report: dict, answers: dict) -> tuple[dict, str]:
    """尝试用 LLM 个人化改写报告文本。

    返回 (report, source)：source = "enriched" | "template"。
    任何失败路径都返回模板版，绝不影响提交主流程。
    """
    if not config.LLM_API_KEY:
        return report, "template"

    try:
        messages = build_rewrite_prompt(report, answers)
        enriched_text = await asyncio.wait_for(
            _call_llm(messages), timeout=ENRICH_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning("报告改写超时(%ss)，回退模板版", ENRICH_TIMEOUT_SECONDS)
        return report, "template"
    except Exception:  # noqa: BLE001 - 兜底：任何异常都不影响提交
        logger.exception("报告改写失败，回退模板版")
        return report, "template"

    allowed_digits = _digits_set(json.dumps(answers, ensure_ascii=False))
    # 答案键是选项 key（A/B/C/D），数字真正出现在选项文本和题目里，一并放行
    from services.assessment_service import ASSESSMENT_QUESTIONS as _Q  # noqa: PLC0415
    for _q in _Q:
        allowed_digits |= _digits_set(json.dumps(_q, ensure_ascii=False))
    validated = _validate_enriched(report, enriched_text, allowed_digits)
    if validated is None:
        return report, "template"
    return validated, "enriched"


async def _call_llm(messages) -> str:
    import agent.llm_client as lc

    return await lc.ask_llm(messages, max_retries=1)
