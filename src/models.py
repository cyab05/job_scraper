from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Location(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    display: str = ""


class Salary(BaseModel):
    minimum: int | None = None
    maximum: int | None = None
    currency: str | None = None
    source: Literal["direct_data", "description"] | None = None


class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    company: str
    company_url: str | None = None
    url: str
    location: Location
    is_remote: bool = False
    salary: Salary = Field(default_factory=Salary)
    description: str = ""
    posted: date | None = None
    employment_type: str | None = None
    job_level: str | None = None
    company_industry: str | None = None


class Category(IntEnum):
    GOOD_FIT = 1
    MEDIUM_FIT = 2
    BAD_FIT = 3
    NOT_RELEVANT = 4


CATEGORY_LABELS: dict[Category, str] = {
    Category.GOOD_FIT: "good_fit",
    Category.MEDIUM_FIT: "medium_fit",
    Category.BAD_FIT: "bad_fit",
    Category.NOT_RELEVANT: "not_relevant",
}


class JobClassification(BaseModel):
    id: str
    category: Category
    category_label: Literal["good_fit", "medium_fit", "bad_fit", "not_relevant"]
    reason: str


class ClassificationResponse(BaseModel):
    classifications: list[JobClassification]


class ClassifiedJob(Job):
    category: Category
    category_label: Literal["good_fit", "medium_fit", "bad_fit", "not_relevant"]
    reason: str


class ClassifiedJobsOutput(BaseModel):
    classified_at: datetime
    summary: dict[str, int]
    jobs: list[ClassifiedJob]
