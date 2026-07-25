"""搜索网络工具。"""

import re

import httpx

from agent.tools.base import BaseTool


class WebSearchTool(BaseTool):
    def get_definition(self):
        return {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "搜索网络获取最新信息，适合查找最新课程、工具、资讯等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词"
                        }
                    },
                    "required": ["query"]
                }
            }
        }

    async def execute(self, query: str, **kwargs) -> str:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    "https://cn.bing.com/search",
                    params={"q": query, "mkt": "zh-CN"},
                    headers=headers,
                )
                resp.raise_for_status()
                text = resp.text

            results = []
            blocks = re.findall(r'<li class="b_algo"[^>]*>.*?</li>', text, re.DOTALL)
            for block in blocks:
                h2 = re.search(r'<h2[^>]*><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>', block, re.DOTALL)
                if not h2:
                    continue
                url = h2.group(1)
                title = re.sub(r'<[^>]+>', '', h2.group(2)).strip()
                p = re.search(r'<p[^>]*class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
                snippet = re.sub(r'<[^>]+>', '', p.group(1)).strip() if p else ""
                results.append(f"**{title}**\n{url}\n{snippet}")

            if not results:
                return f"未找到关于「{query}」的相关信息，建议用户自行搜索。"

            return "\n\n---\n\n".join(results[:5])
        except Exception as e:
            return f"搜索失败：{str(e)}"
