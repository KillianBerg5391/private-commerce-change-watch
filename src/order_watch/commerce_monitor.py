import hashlib
import difflib
import json
import re
from pathlib import Path
from typing import Protocol

from .models import WatchRequest, WatchResult


class ChangeGateway(Protocol):
    async def scrape(self, url: str) -> str:
        raise RuntimeError("Protocol method called directly")

    async def send_change_alert(
        self, *, to: str, subject: str, text: str, idempotency_key: str
    ) -> str:
        raise RuntimeError("Protocol method called directly")


class CommerceMonitor:
    def __init__(self, gateway: ChangeGateway, state_file: Path) -> None:
        self._gateway = gateway
        self._state_file = state_file

    async def check(self, request: WatchRequest) -> WatchResult:
        url = str(request.url)
        page = await self._gateway.scrape(url)
        comparison_text = self._comparison_text(page)
        digest = hashlib.sha256(comparison_text.encode("utf-8")).hexdigest()
        states = self._read_states()
        previous = states.get(url)

        if previous is not None and previous["digest"] == digest:
            return WatchResult(state="unchanged", page_digest=digest)

        states[url] = {"digest": digest, "text": comparison_text}
        self._write_states(states)
        if previous is None:
            return WatchResult(state="baseline_created", page_digest=digest)

        order = request.customer_update.order_reference
        changed_lines = list(
            difflib.unified_diff(
                previous["text"].splitlines(),
                comparison_text.splitlines(),
                fromfile="previous",
                tofile="current",
                lineterm="",
            )
        )[:40]
        page_diff = "\n".join(changed_lines)
        text = (
            f"The monitored commerce page changed.\n\n"
            f"Order: {order}\n"
            f"Expected state: {request.customer_update.expected_state}\n"
            f"Checkout: {request.checkout.stage}\n"
            f"Fulfillment: {request.fulfillment.status}\n"
            f"Receipt issued: {request.receipt.issued}\n"
            f"Page: {url}\n"
            f"Previous digest: {previous['digest']}\n"
            f"Current digest: {digest}\n"
            f"\nChange summary:\n{page_diff}\n"
        )
        message_id = await self._gateway.send_change_alert(
            to=str(request.alert_to),
            subject=f"Order page changed: {order}",
            text=text,
            idempotency_key=f"page-change-{digest}",
        )
        return WatchResult(
            state="changed", page_digest=digest, alert_message_id=message_id
        )

    @staticmethod
    def _comparison_text(page: str) -> str:
        redacted = re.sub(
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
            "[email]",
            page,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(r"\b\d{12,19}\b", "[long-number]", redacted)
        return "\n".join(line.strip() for line in redacted.splitlines() if line.strip())

    def _read_states(self) -> dict[str, dict[str, str]]:
        if not self._state_file.exists():
            return {}
        value = json.loads(self._state_file.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not all(
            isinstance(key, str)
            and isinstance(item, dict)
            and isinstance(item.get("digest"), str)
            and isinstance(item.get("text"), str)
            for key, item in value.items()
        ):
            raise ValueError("State file must contain comparison records")
        return value

    def _write_states(self, states: dict[str, dict[str, str]]) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(states, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._state_file)
