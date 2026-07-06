from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from typing import Any

from jobspy import scrape_jobs

from src.config import ScraperConfig
from src.models import Job, Location, Salary


EMPLOYMENT_TYPE_MAP = {
    "fulltime": "Full-time",
    "parttime": "Part-time",
    "internship": "Internship",
    "contract": "Contract",
}


def run_scrape(config: ScraperConfig) -> list[Job]:
    kwargs: dict[str, Any] = {
        "site_name": [config.site_name],
        "search_term": config.search_term,
        "location": config.location,
        "distance": config.distance,
        "results_wanted": config.results_wanted,
        "hours_old": config.hours_old,
        "linkedin_fetch_description": config.linkedin_fetch_description,
        "description_format": config.description_format,
        "verbose": 1,
    }
    if config.is_remote is not None:
        kwargs["is_remote"] = config.is_remote
    if config.enforce_annual_salary is not None:
        kwargs["enforce_annual_salary"] = config.enforce_annual_salary

    jobs_df = scrape_jobs(**kwargs)

    seen_urls: set[str] = set()
    jobs: list[Job] = []
    for row in jobs_df.to_dict(orient="records"):
        job = _normalize_row(row)
        if not job or job.url in seen_urls:
            continue
        seen_urls.add(job.url)
        jobs.append(job)
    return jobs


def _normalize_row(row: dict[str, Any]) -> Job | None:
    url = _as_str(row.get("job_url"))
    if not url:
        return None

    location = _parse_location(row)
    salary = _parse_salary(row)

    return Job(
        id=_job_id(url),
        title=_as_str(row.get("title")) or "Unknown title",
        company=_as_str(row.get("company")) or "Unknown company",
        company_url=_as_str(row.get("company_url")),
        url=url,
        location=location,
        is_remote=bool(row.get("is_remote")),
        salary=salary,
        description=_as_str(row.get("description")) or "",
        posted=_parse_date(row.get("date_posted")),
        employment_type=_employment_type(row.get("job_type")),
        job_level=_as_str(row.get("job_level")),
        company_industry=_as_str(row.get("company_industry")),
    )


def _job_id(url: str) -> str:
    return sha256(url.encode("utf-8")).hexdigest()[:12]


def _parse_location(row: dict[str, Any]) -> Location:
    location_payload = row.get("location")
    if isinstance(location_payload, dict):
        city = _as_str(location_payload.get("city"))
        state = _as_str(location_payload.get("state"))
        country = _as_str(location_payload.get("country"))
    else:
        city = _as_str(row.get("city"))
        state = _as_str(row.get("state"))
        country = _as_str(row.get("country"))
    is_remote = bool(row.get("is_remote"))
    parts = [part for part in [city, state, country] if part]
    display = ", ".join(parts)
    if is_remote and display:
        display = f"{display} (Remote)"
    elif is_remote:
        display = "Remote"
    return Location(city=city, state=state, country=country, display=display)


def _parse_salary(row: dict[str, Any]) -> Salary:
    compensation = row.get("job_function")
    if isinstance(compensation, dict):
        minimum = _to_int(compensation.get("min_amount"))
        maximum = _to_int(compensation.get("max_amount"))
        currency = _as_str(compensation.get("currency"))
        source = _as_str(compensation.get("salary_source"))
    else:
        minimum = _to_int(row.get("min_amount"))
        maximum = _to_int(row.get("max_amount"))
        currency = _as_str(row.get("currency"))
        source = _as_str(row.get("salary_source"))

    if currency and currency.upper() != "USD":
        minimum = None
        maximum = None

    if source not in {"direct_data", "description"}:
        source = None

    return Salary(
        minimum=minimum,
        maximum=maximum,
        currency=currency,
        source=source,  # type: ignore[arg-type]
    )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    as_str = _as_str(value)
    if not as_str:
        return None
    try:
        return datetime.fromisoformat(as_str).date()
    except ValueError:
        return None


def _employment_type(value: Any) -> str | None:
    raw = _as_str(value)
    if not raw:
        return None
    return EMPLOYMENT_TYPE_MAP.get(raw.lower(), raw)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
