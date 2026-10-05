import asyncio
from pathlib import Path

from order_watch.commerce_monitor import CommerceMonitor
from order_watch.models import WatchRequest


class RecordingGateway:
    def __init__(self, pages: list[str]) -> None:
        self.pages = iter(pages)
        self.alerts: list[dict[str, str]] = []

    async def scrape(self, url: str) -> str:
        return next(self.pages)

    async def send_change_alert(
        self, *, to: str, subject: str, text: str, idempotency_key: str
    ) -> str:
        self.alerts.append(
            {"to": to, "subject": subject, "text": text, "key": idempotency_key}
        )
        return "msg_change_01"


def watch_request() -> WatchRequest:
    return WatchRequest.model_validate(
        {
            "url": "https://shop.example/orders/ORD-42",
            "alert_to": "care@example.com",
            "checkout": {"cart_reference": "CART-42", "stage": "confirmed"},
            "fulfillment": {"method": "ship", "status": "processing"},
            "receipt": {"reference": "REC-42", "issued": True},
            "customer_update": {
                "order_reference": "ORD-42",
                "expected_state": "dispatched",
            },
        }
    )


def test_alert_only_after_page_content_changes(tmp_path: Path) -> None:
    asyncio.run(run_change_scenario(tmp_path))


async def run_change_scenario(tmp_path: Path) -> None:
    gateway = RecordingGateway(
        ["Order ORD-42: processing", "Order ORD-42: processing", "Order ORD-42: dispatched"]
    )
    monitor = CommerceMonitor(gateway, tmp_path / "states.json")
    request = watch_request()

    first = await monitor.check(request)
    same = await monitor.check(request)
    changed = await monitor.check(request)

    assert first.state == "baseline_created"
    assert same.state == "unchanged"
    assert changed.state == "changed"
    assert changed.alert_message_id == "msg_change_01"
    assert len(gateway.alerts) == 1
    assert "ORD-42" in gateway.alerts[0]["subject"]
    assert "-Order ORD-42: processing" in gateway.alerts[0]["text"]
    assert "+Order ORD-42: dispatched" in gateway.alerts[0]["text"]
    assert gateway.alerts[0]["key"].startswith("page-change-")
