from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ScraperConfig(BaseModel):
    site_name: Literal["linkedin"] = "linkedin"
    locations: list[str]
    search_term: str
    results_wanted: int = 50
    distance: int = 50
    is_remote: bool | None = None
    hours_old: int = 48
    linkedin_fetch_description: bool = True
    enforce_annual_salary: bool | None = None
    description_format: Literal["markdown", "html"] = "markdown"
    include_remote_pass: bool = True
    remote_location_seed: str = "United States"

    @model_validator(mode="before")
    @classmethod
    def _migrate_single_location(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "locations" not in data and "location" in data:
            single_location = data.get("location")
            data["locations"] = [single_location] if single_location else []
        return data


class HardFilterConfig(BaseModel):
    countries: list[str]
    keywords_exclude: list[str]
    banned_companies: list[str]
    require_us_location: bool = True


class SalaryRange(BaseModel):
    minimum: int
    maximum: int


class IdealFilterConfig(BaseModel):
    locations: list[str]
    salary: SalaryRange
    max_years_experience: int


class FiltersConfig(BaseModel):
    hard: HardFilterConfig
    ideal: IdealFilterConfig


class LLMConfig(BaseModel):
    provider: Literal["gemini"] = "gemini"
    model: str
    max_token_batch: int = 100_000
    batch_interval_seconds: int = 60


class EmailConfig(BaseModel):
    recipient: str
    sender: str


class ScheduleConfig(BaseModel):
    timezone: str
    time: str


class AppConfig(BaseModel):
    scraper: ScraperConfig
    filters: FiltersConfig
    llm: LLMConfig
    email: EmailConfig
    schedule: ScheduleConfig = Field(
        default_factory=lambda: ScheduleConfig(timezone="America/Los_Angeles", time="08:00")
    )


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
