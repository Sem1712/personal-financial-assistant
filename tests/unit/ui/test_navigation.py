import re

import httpx
import pytest

from personal_financial_assistant.ui.app import create_app


@pytest.mark.asyncio
async def test_chat_and_report_endpoints_are_not_implemented() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        page = await client.get("/")
        match = re.search(r'<meta name="pfa-token" content="([^"]+)">', page.text)
        assert match is not None
        assert "__PFA_TOKEN__" not in page.text
        headers = {"origin": "http://127.0.0.1:8765", "x-pfa-token": match.group(1)}
        for path in ("/api/chat", "/api/reports"):
            assert (
                await client.post(path, headers=headers, json={})
            ).status_code == 404
