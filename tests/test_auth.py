"""auth.py 测试：认证开关、Header/Query 传参、拒绝无 key 请求。"""

import pytest
from unittest.mock import patch
from tests.conftest import parse_sse_events


@pytest.mark.asyncio
async def test_auth_disabled_allows_all(app_client):
    """API_KEY 为空时，所有请求放行。"""
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": "auth-test-1", "message": "你好"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_rejects_no_key(app_client):
    """API_KEY 已设置时，无 key 的请求返回 401。"""
    with patch("auth.API_KEY", "test-secret-123"):
        resp = await app_client.post(
            "/api/chat",
            json={"session_id": "auth-test-2", "message": "你好"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_accepts_header(app_client):
    """API_KEY 已设置时，通过 Header 传入正确 key 放行。"""
    with patch("auth.API_KEY", "test-secret-123"):
        resp = await app_client.post(
            "/api/chat",
            json={"session_id": "auth-test-3", "message": "你好"},
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_accepts_query(app_client):
    """API_KEY 已设置时，通过 Query 传入正确 key 放行。"""
    with patch("auth.API_KEY", "test-secret-123"):
        resp = await app_client.post(
            "/api/chat?api_key=test-secret-123",
            json={"session_id": "auth-test-4", "message": "你好"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_rejects_wrong_key(app_client):
    """API_KEY 已设置时，错误的 key 返回 401。"""
    with patch("auth.API_KEY", "test-secret-123"):
        resp = await app_client.post(
            "/api/chat",
            json={"session_id": "auth-test-5", "message": "你好"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_template_pages_no_auth(app_client):
    """模板页面（/, /chat）不受认证影响。"""
    with patch("auth.API_KEY", "test-secret-123"):
        resp = await app_client.get("/")
        assert resp.status_code == 200

        resp = await app_client.get("/chat")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_evaluation_endpoints(app_client):
    """评估端点也需要认证。"""
    with patch("auth.API_KEY", "test-secret-123"):
        # 无 key → 401
        resp = await app_client.post(
            "/evaluation/start",
            json={"session_id": "auth-eval-1", "message": "评估"},
        )
        assert resp.status_code == 401

        # 有 key → 200
        resp = await app_client.post(
            "/evaluation/start",
            json={"session_id": "auth-eval-1", "message": "评估"},
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_session_endpoints(app_client):
    """Session 端点也需要认证。"""
    with patch("auth.API_KEY", "test-secret-123"):
        # 无 key → 401
        resp = await app_client.get("/api/session/test/state")
        assert resp.status_code == 401

        # 有 key → 200
        resp = await app_client.get(
            "/api/session/test/state",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
