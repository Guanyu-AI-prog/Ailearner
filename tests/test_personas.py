"""
ailearner 入门测试 —— 3 个不同人设完整交互流程
"""
import json
import httpx
import uuid
import time
import sys

API_BASE = "http://127.0.0.1:8000"

# ==================== 3 个人设定义 ====================

PERSONAS = [
    {
        "name": "Persona A — 职场小白想转行",
        "description": "文科背景，非技术岗，想转行做AI相关工作，数学/编程零基础",
        "messages": [
            "我想学AI，不知道适不适合，帮我评估一下",
            "1",   # 学AI
            "1",   # 想转行做AI相关工作
            "3",   # 文科/商科/艺术
            "2",   # 每周2-5小时
            "5",   # 对数学没信心
            "1",   # 零基础，没写过代码
            "1",   # 零成本，只用免费资源
            "6",   # 还没特定方向，想全面了解
        ],
    },
    {
        "name": "Persona B — 大学生好奇AI",
        "description": "大三计算机专业学生，对AI感兴趣，有一定编程基础",
        "messages": [
            "你好，我想了解一下学AI的路径",
            "1",   # 学AI
            "5",   # 还没想清楚，先了解看看
            "4",   # 学生
            "3",   # 5-10小时
            "2",   # 大学学过高等数学/线性代数（还记得一些）
            "3",   # 会写基本的Python代码
            "3",   # 愿意花钱买课/算力
            "1",   # 文字相关（NLP）
        ],
    },
    {
        "name": "Persona C — 在职想用AI提效",
        "description": "产品经理，在职，不想学底层，只想把AI当工具用",
        "messages": [
            "我平时工作需要写文档、做汇报，有没有AI工具能帮我提效？",
            "1",   # 选场景1: 文章修改/润色/重写
        ],
    },
]


def parse_sse_events(raw_text: str):
    """Parse SSE response text into list of events."""
    events = []
    current_data = None
    for line in raw_text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            current_data = line[5:].strip()
        elif line == "" and current_data is not None:
            try:
                obj = json.loads(current_data)
                events.append(obj)
            except json.JSONDecodeError:
                pass
            current_data = None
    if current_data is not None:
        try:
            obj = json.loads(current_data)
            events.append(obj)
        except json.JSONDecodeError:
            pass
    return events


def send_message(session_id: str, message: str, timeout: float = 120.0) -> dict:
    """Send a message to the chat API and return the full response."""
    url = f"{API_BASE}/api/chat"
    payload = {"session_id": session_id, "message": message}

    full_text = ""
    status_msgs = []

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        raw = resp.text

    events = parse_sse_events(raw)
    for evt in events:
        if evt.get("type") == "content":
            full_text += evt.get("text", "")
        elif evt.get("type") == "status":
            status_msgs.append(evt.get("text", ""))
        elif evt.get("type") == "done":
            pass

    return {
        "full_text": full_text,
        "status_msgs": status_msgs,
        "event_count": len(events),
    }


def reset_session(session_id: str):
    """Reset a session."""
    with httpx.Client(timeout=10) as client:
        client.post(f"{API_BASE}/api/session/{session_id}/reset")


def run_persona_test(persona: dict) -> dict:
    """Run a full test for one persona and return results."""
    session_id = f"test_{uuid.uuid4().hex[:12]}"
    results = {
        "persona": persona["name"],
        "description": persona["description"],
        "session_id": session_id,
        "interactions": [],
        "final_state": None,
    }

    print(f"\n{'='*60}")
    print(f"  测试人设: {persona['name']}")
    print(f"  描述: {persona['description']}")
    print(f"  Session: {session_id}")
    print(f"{'='*60}")

    for i, msg in enumerate(persona["messages"]):
        print(f"\n--- 第 {i+1} 轮 ---")
        print(f"[用户] {msg}")

        resp = send_message(session_id, msg)

        print(f"[AI回复]\n{resp['full_text'][:500]}{'...' if len(resp['full_text']) > 500 else ''}")
        if resp["status_msgs"]:
            print(f"[状态] {' | '.join(resp['status_msgs'][:3])}")

        results["interactions"].append({
            "round": i + 1,
            "user_message": msg,
            "ai_response": resp["full_text"],
            "status_msgs": resp["status_msgs"],
        })

        time.sleep(0.5)  # 避免速率限制

    # 查询最终会话状态
    with httpx.Client(timeout=10) as client:
        state_resp = client.get(f"{API_BASE}/api/session/{session_id}/state")
        results["final_state"] = state_resp.json()

    print(f"\n[最终状态] evaluation_done={results['final_state'].get('evaluation_done')}, "
          f"evaluation_started={results['final_state'].get('evaluation_started')}, "
          f"phase={results['final_state'].get('evaluation_phase')}")

    reset_session(session_id)
    print(f"[已重置会话 {session_id}]")

    return results


def main():
    all_results = []

    for persona in PERSONAS:
        try:
            result = run_persona_test(persona)
            all_results.append(result)
        except Exception as e:
            print(f"\n!!! 测试失败: {persona['name']}: {e}")
            all_results.append({
                "persona": persona["name"],
                "error": str(e),
            })

    # 保存完整结果
    output_path = "/home/admin/ailearner/test_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n\n{'='*60}")
    print(f"  测试完成，结果已保存到 {output_path}")
    print(f"{'='*60}")

    # 打印汇总
    print("\n--- 测试汇总 ---")
    for r in all_results:
        if "error" in r:
            print(f"  {r['persona']}: FAILED - {r['error']}")
        else:
            state = r.get("final_state", {})
            print(f"  {r['persona']}:")
            print(f"    交互轮数: {len(r['interactions'])}")
            print(f"    评估完成: {state.get('evaluation_done', 'N/A')}")
            print(f"    评估路径: {state.get('evaluation_path', 'N/A')}")
            report_preview = state.get("evaluation_report", "")
            if report_preview:
                print(f"    评估报告(前100字): {report_preview[:100]}...")


if __name__ == "__main__":
    main()
