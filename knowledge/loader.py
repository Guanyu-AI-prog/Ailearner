import re
from pathlib import Path
from typing import Dict, List, Tuple


CHUNK_TEMPLATE = """标题：{title}
类型：{type}
方向：{direction}
水平：{level}

{content}"""

LEVEL_PATTERN = re.compile(r'(L[1-4])')


def _extract_level(title: str) -> str:
    match = LEVEL_PATTERN.search(title)
    if match:
        return match.group(1)
    if '科普' in title:
        return 'L1'
    if '入门' in title:
        return 'L2'
    if '进阶' in title:
        return 'L3'
    if '专业' in title:
        return 'L4'
    return ''


def parse_markdown(filepath: Path) -> List[Dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    chunks = []
    lines = content.split("\n")
    current_section = ""
    current_title = ""
    current_type = ""
    current_level = ""
    buffer = []

    def flush():
        if not buffer:
            return None
        text = "\n".join(buffer).strip()
        if not text:
            return None
        return {
            "title": current_title or current_section,
            "type": current_type,
            "direction": current_section,
            "level": current_level or _extract_level(current_title),
            "content": text,
        }

    for line in lines:
        if line.startswith("## "):
            chunk = flush()
            if chunk:
                chunks.append(chunk)
            current_section = line.lstrip("#").strip()
            current_title = ""
            current_type = ""
            current_level = ""
            buffer = []
        elif line.startswith("### "):
            chunk = flush()
            if chunk:
                chunks.append(chunk)
            raw_title = line.lstrip("#").strip()
            current_title = raw_title.lstrip("0123456789. ")
            current_level = _extract_level(raw_title)
            buffer = []
        elif line.startswith("- [") and "]" in line:
            match = re.match(r"- \[(.+?)\]\((.+?)\) - (.+) - (.+)", line)
            if match:
                title = match.group(1)
                url = match.group(2)
                res_type = match.group(3)
                desc = match.group(4)
                buffer.append(f"- **{title}**（{url}）- {res_type} - {desc}")
                if not current_title:
                    current_title = title
                current_type = current_type or res_type
            else:
                buffer.append(line)
        elif line.startswith("- "):
            buffer.append(line)
        elif line.strip() == "":
            if buffer:
                buffer.append("")
        else:
            if line.startswith("# "):
                continue
            if line.strip():
                buffer.append(line)

    chunk = flush()
    if chunk:
        chunks.append(chunk)

    return chunks


def get_chunks_text(chunks: List[Dict]) -> Tuple[List[str], List[Dict]]:
    texts = []
    metadatas = []
    seen = set()
    for chunk in chunks:
        text = chunk["content"]
        if not text or text in seen:
            continue
        seen.add(text)
        level = chunk.get("level") or "L1"
        direction = chunk.get("direction") or "通用"
        res_type = chunk.get("type") or "通用"
        full_text = CHUNK_TEMPLATE.format(
            title=chunk["title"],
            type=res_type,
            direction=direction,
            level=level,
            content=text
        )
        texts.append(full_text)
        metadatas.append({
            "title": chunk["title"],
            "type": res_type,
            "direction": direction,
            "level": level,
        })
    return texts, metadatas
