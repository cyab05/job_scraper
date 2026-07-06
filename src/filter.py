from __future__ import annotations

from src.config import HardFilterConfig
from src.models import Job


def apply_hard_filters(jobs: list[Job], config: HardFilterConfig) -> list[Job]:
    filtered: list[Job] = []
    for job in jobs:
        if _is_missing_url(job):
            continue
        if _fails_country_check(job, config):
            continue
        if _matches_excluded_title(job, config.keywords_exclude):
            continue
        if _matches_banned_company(job, config.banned_companies):
            continue
        filtered.append(job)
    return filtered


def _is_missing_url(job: Job) -> bool:
    return not bool(job.url.strip())


def _fails_country_check(job: Job, config: HardFilterConfig) -> bool:
    if not config.require_us_location:
        return False
    country = (job.location.country or "").strip().lower()
    if not country:
        return True
    allowed = {c.strip().lower() for c in config.countries}
    return country not in allowed


def _matches_excluded_title(job: Job, excluded_keywords: list[str]) -> bool:
    title = job.title.lower()
    return any(keyword.lower() in title for keyword in excluded_keywords)


def _matches_banned_company(job: Job, banned_companies: list[str]) -> bool:
    company = job.company.lower()
    return any(company_name.lower() in company for company_name in banned_companies)
