"""轻量认证：API Key 模式，可通过环境变量开关。

- 未设置 API_KEY 时跳过认证（开发模式）
- 支持 Header: Authorization: Bearer <key>
- 支持 Query: ?api_key=<key>（用于 SSE 等不方便设 Header 的场景）
"""

import hmac
import os

from fastapi import HTTPException, Request

API_KEY = os.getenv("API_KEY", "")


async def verify_auth(request: Request):
    """认证依赖项。API_KEY 为空时跳过认证。"""
    if not API_KEY:
        return

    # 从 Header 获取
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], API_KEY):
        return

    # 从 Query 获取（SSE fallback）
    key = request.query_params.get("api_key")
    if key and hmac.compare_digest(key, API_KEY):
        return

    raise HTTPException(status_code=401, detail="Unauthorized")
