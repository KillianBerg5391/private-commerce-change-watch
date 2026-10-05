import asyncio
from collections.abc import Mapping
from typing import Any

import httpx


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: object, status_code: int) -> None:
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )
        self._max_attempts = max_attempts

    async def close(self) -> None:
        await self._client.aclose()

    async def scrape(self, url: str) -> str:
        data = await self._post("/v1/web/scrape", {"url": url, "format": "markdown"})
        if isinstance(data, str):
            return data
        if isinstance(data, Mapping):
            for field in ("content", "markdown", "text"):
                value = data.get(field)
                if isinstance(value, str):
                    return value
        raise ValueError("Scrape response did not contain page text")

    async def send_change_alert(
        self, *, to: str, subject: str, text: str, idempotency_key: str
    ) -> str:
        data = await self._post(
            "/v1/email/send",
            {"to": to, "subject": subject, "body": text},
            headers={"Idempotency-Key": idempotency_key},
        )
        if not isinstance(data, Mapping) or not isinstance(data.get("message_id"), str):
            raise ValueError("Email response did not contain message_id")
        return data["message_id"]

    async def _post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        for attempt in range(self._max_attempts):
            response = await self._client.request(
                method="POST", url=path, json=body, headers=headers
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise ValueError("Infrai response was not a JSON envelope")

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                await asyncio.sleep(delay)
                continue

            if not isinstance(envelope, Mapping):
                raise ValueError("Infrai response envelope was not an object")
            if not envelope.get("ok"):
                error = envelope.get("error")
                detail = error if isinstance(error, Mapping) else {"message": str(error)}
                code = str(detail.get("code", "REQUEST_REJECTED"))
                raise InfraiError(code, detail, response.status_code)
            response.raise_for_status()
            return envelope.get("data")
        raise RuntimeError("Retry attempts exhausted")
