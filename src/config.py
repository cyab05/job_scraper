from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ScraperConfig(BaseModel):
    site_name: Literal["linkedin"] = "linkedin"
    location: str
    search_term: str
    results_wanted: int = 50
    distance: int = 50
    is_remote: bool | None = None
    hours_old: int = 48
    linkedin_fetch_description: bool = True
    enforce_annual_salary: bool | None = None
    description_format: Literal["markdown", "html"] = "markdown"


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
    provider: Literal["groq"] = "groq"
    model: str
    batch_size: int = 20


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
    schedule: ScheduleConfig


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
