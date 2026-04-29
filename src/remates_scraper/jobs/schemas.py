"""Pydantic schemas used to validate raw_listings before promoting."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

PROVINCES = {"San José", "Alajuela", "Cartago", "Heredia", "Guanacaste", "Puntarenas", "Limón"}


class AuctionInput(BaseModel):
    round: int = Field(ge=1, le=3)
    scheduled_at: datetime | None = None
    location_text: str | None = None
    base_price: float = Field(gt=0)
    currency: Literal["CRC", "USD"]


class ListingInput(BaseModel):
    title: str = Field(min_length=3)
    description: str | None = None
    property_type: Literal[
        "casa", "apartamento", "lote", "local_comercial",
        "oficina", "industrial", "finca", "otro",
    ]
    province: str
    canton: str | None = None
    distrito: str | None = None
    address_text: str | None = None
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    parking_spots: int | None = Field(default=None, ge=0)
    lot_size_m2: float | None = Field(default=None, ge=0)
    construction_size_m2: float | None = Field(default=None, ge=0)
    base_price: float = Field(gt=0)
    currency: Literal["CRC", "USD"]
    source_url: HttpUrl | None = None
    image_urls: list[str] = Field(default_factory=list)
    for_sale_kind: Literal["auction", "direct_sale"]
    auctions: list[AuctionInput] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("province")
    @classmethod
    def province_must_be_valid(cls, v: str) -> str:
        if v not in PROVINCES:
            raise ValueError(f"invalid province: {v}")
        return v

    @model_validator(mode="after")
    def auctions_required_for_auction_kind(self) -> ListingInput:
        if self.for_sale_kind == "auction" and not self.auctions:
            raise ValueError("for_sale_kind='auction' requires at least one auction entry")
        return self
