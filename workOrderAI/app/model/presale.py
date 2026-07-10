from typing import Literal

from pydantic import BaseModel, Field


class PresaleState(BaseModel):
    budget_min: float | None = None
    budget_max: float | None = None
    budget_target: float | None = None
    budget_flexible: bool = True
    budget_unlimited: bool = False
    home_size_sqm: int | None = None
    home_size_level: Literal["SMALL", "MEDIUM", "LARGE"] | None = None
    floor_types: list[str] = Field(default_factory=list)
    has_pet: bool | None = None
    station_preference: bool | None = None
    noise_sensitive: bool | None = None
    candidate_sku_ids: list[str] = Field(default_factory=list)
    candidate_names: list[str] = Field(default_factory=list)


class PresaleNeedExtraction(BaseModel):
    budget_min: float | None = None
    budget_max: float | None = None
    budget_target: float | None = None
    budget_flexible: bool | None = None
    budget_unlimited: bool | None = None
    home_size_sqm: int | None = None
    home_size_level: Literal["SMALL", "MEDIUM", "LARGE"] | None = None
    floor_types: list[str] | None = None
    has_pet: bool | None = None
    station_preference: bool | None = None
    noise_sensitive: bool | None = None
    intent: Literal["CLARIFY_NEED", "RECOMMEND", "COMPARE", "PRODUCT_QA"] | None = None


class PresaleProduct(BaseModel):
    product_id: str
    sku_id: str
    name: str
    sku_name: str
    category: str
    summary: str
    image_url: str
    price: float
    stock: int
    attributes: dict = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PresaleComparisonRow(BaseModel):
    label: str
    values: list[str]


class PresaleComparison(BaseModel):
    product_names: list[str]
    rows: list[PresaleComparisonRow]
    recommendation: str
