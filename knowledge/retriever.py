import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from config import config


STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "怎么", "什么", "为什么", "如何", "哪", "哪个", "谁", "多少", "几",
    "能", "可以", "应该", "需要", "想", "做", "让", "把", "被", "将",
    "从", "对", "与", "为", "以", "及", "等", "或", "但", "如果", "因为",
    "所以", "虽然", "然后", "之后", "之", "中", "时", "而", "比", "更",
    "吗", "啊", "呢", "吧", "嗯", "哦", "哈", "呀",
    "请", "帮", "给", "向", "用", "还", "已经", "正在", "经过", "通过",
    "可能", "大概", "比较", "非常", "太", "最", "更", "越",
    "一些", "这个", "那个", "这些", "那些", "每个",
    "目前", "现在", "之前", "之后", "以前", "以后", "未来",
    "毕竟", "其实", "当然", "确实", "真的", "主要",
}

_tags: Dict[str, List[str]] = {}
_article_texts: Dict[str, str] = {}
_article_titles: Dict[str, str] = {}
_loaded = False


def _load():
    global _tags, _article_texts, _article_titles, _loaded
    if _loaded:
        return
    _loaded = True

    tags_path = config.KNOWLEDGE_DIR.parent / "tags.json"
    if tags_path.exists():
        with open(tags_path, "r", encoding="utf-8") as f:
            _tags = json.load(f)

    data_dir = config.KNOWLEDGE_DIR
    if not data_dir.exists():
        return
    for fpath in sorted(data_dir.glob("*.md")):
        stem = fpath.stem
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        _article_texts[stem] = content
        title = stem
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line.lstrip("#").strip()
                break
        _article_titles[stem] = title


def _extract_keywords(text: str) -> List[str]:
    tokens = []
    for match in re.finditer(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text):
        token = match.group().lower().strip()
        if token and token not in STOP_WORDS:
            tokens.append(token)
    return tokens


def is_knowledge_ready() -> bool:
    _load()
    return len(_tags) > 0 and len(_article_texts) > 0


def retrieve_knowledge(query: str, n_results: int = 3) -> List[Tuple[str, Dict]]:
    _load()
    if not _tags or not _article_texts:
        return []

    keywords = _extract_keywords(query)
    if not keywords:
        return []

    scored = []
    for stem, tags in _tags.items():
        if stem not in _article_texts:
            continue
        score = 0
        for kw in keywords:
            for tag in tags:
                if kw in tag.lower() or tag.lower() in kw:
                    score += 1
        if score > 0:
            scored.append((score, stem))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, stem in scored[:n_results]:
        results.append((
            _article_texts[stem],
            {"title": _article_titles.get(stem, stem), "tags": _tags.get(stem, [])}
        ))
    return results
