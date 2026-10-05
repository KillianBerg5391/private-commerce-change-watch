from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class CheckoutContext(BaseModel):
    cart_reference: str = Field(min_length=1, max_length=80)
    stage: Literal["cart", "payment", "confirmed"]


class FulfillmentContext(BaseModel):
    method: Literal["ship", "pickup", "digital"]
    status: Literal["pending", "processing", "dispatched", "delivered"]


class ReceiptContext(BaseModel):
    reference: str = Field(min_length=1, max_length=80)
    issued: bool


class CustomerUpdate(BaseModel):
    order_reference: str = Field(min_length=1, max_length=80)
    expected_state: str = Field(min_length=1, max_length=120)


class WatchRequest(BaseModel):
    url: HttpUrl
    alert_to: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )
    checkout: CheckoutContext
    fulfillment: FulfillmentContext
    receipt: ReceiptContext
    customer_update: CustomerUpdate


class WatchResult(BaseModel):
    state: Literal["baseline_created", "unchanged", "changed"]
    page_digest: str
    alert_message_id: str | None = None
