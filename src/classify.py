from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from groq import Groq
from pypdf import PdfReader

from src.config import IdealFilterConfig, LLMConfig
from src.models import (
    CATEGORY_LABELS,
    Category,
    ClassifiedJob,
    ClassifiedJobsOutput,
    ClassificationResponse,
    Job,
)


def extract_resume_text(resume_path: Path) -> str:
    reader = PdfReader(str(resume_path))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(page_text.strip())
    text = "\n\n".join([chunk for chunk in pages if chunk]).strip()
    if not text:
        raise ValueError(f"No text extracted from resume file: {resume_path}")
    return text


def load_system_prompt(template_path: Path, resume_text: str, ideal: IdealFilterConfig) -> str:
    template = template_path.read_text(encoding="utf-8")
    rendered = template.replace("{resume_text}", resume_text)
    rendered = rendered.replace("{ideal.max_years_experience}", str(ideal.max_years_experience))
    rendered = rendered.replace("{ideal.salary.minimum}", str(ideal.salary.minimum))
    rendered = rendered.replace("{ideal.salary.maximum}", str(ideal.salary.maximum))
    rendered = rendered.replace("{ideal.locations}", ", ".join(ideal.locations))
    return rendered


def classify_jobs(
    jobs: list[Job],
    llm: LLMConfig,
    ideal: IdealFilterConfig,
    prompt_template_path: Path,
    resume_path: Path,
) -> ClassifiedJobsOutput:
    if not jobs:
        return ClassifiedJobsOutput(classified_at=datetime.now(), summary=_empty_summary(), jobs=[])

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required environment variable: GROQ_API_KEY")

    resume_text = extract_resume_text(resume_path)
    system_prompt = load_system_prompt(prompt_template_path, resume_text, ideal)
    client = Groq(api_key=api_key)

    by_id: dict[str, Job] = {job.id: job for job in jobs}
    classified_jobs: list[ClassifiedJob] = []

    for chunk in _chunk(jobs, llm.batch_size):
        payload = json.dumps([_job_for_prompt(job) for job in chunk], ensure_ascii=False)
        response = _request_classification(client, llm.model, system_prompt, payload)
        for item in response.classifications:
            job = by_id.get(item.id)
            if not job:
                continue
            label = CATEGORY_LABELS[item.category]
            classified_jobs.append(
                ClassifiedJob(
                    **job.model_dump(),
                    category=item.category,
                    category_label=label,
                    reason=item.reason.strip(),
                )
            )

    # Any missing IDs default to not_relevant to keep output stable.
    classified_ids = {job.id for job in classified_jobs}
    for job in jobs:
        if job.id in classified_ids:
            continue
        classified_jobs.append(
            ClassifiedJob(
                **job.model_dump(),
                category=Category.NOT_RELEVANT,
                category_label="not_relevant",
                reason="No model classification returned for this job.",
            )
        )

    summary = _summarize(classified_jobs)
    return ClassifiedJobsOutput(classified_at=datetime.now(), summary=summary, jobs=classified_jobs)


def _request_classification(client: Groq, model: str, system_prompt: str, payload: str) -> ClassificationResponse:
    response_text = _chat_completion(client, model, system_prompt, payload)
    parsed = _parse_response(response_text)
    if parsed:
        return parsed

    retry_payload = f"{payload}\n\nReturn valid JSON only. Do not include markdown."
    retry_text = _chat_completion(client, model, system_prompt, retry_payload)
    parsed_retry = _parse_response(retry_text)
    if parsed_retry:
        return parsed_retry
    raise ValueError("LLM response could not be parsed as ClassificationResponse after one retry.")


def _chat_completion(client: Groq, model: str, system_prompt: str, payload: str) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        temperature=0.1,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Empty response from LLM.")
    return content.strip()


def _parse_response(response_text: str) -> ClassificationResponse | None:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    try:
        return ClassificationResponse.model_validate(parsed)
    except Exception:
        return None


def _job_for_prompt(job: Job) -> dict[str, Any]:
    description = job.description or ""
    if len(description) > 2000:
        description = description[:2000]

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location.model_dump(),
        "salary": job.salary.model_dump(),
        "description": description,
        "job_level": job.job_level,
        "url": job.url,
    }


def _chunk(items: list[Job], chunk_size: int) -> list[list[Job]]:
    if chunk_size <= 0:
        return [items]
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _empty_summary() -> dict[str, int]:
    return {label: 0 for label in ("good_fit", "medium_fit", "bad_fit", "not_relevant")}


def _summarize(jobs: list[ClassifiedJob]) -> dict[str, int]:
    summary = _empty_summary()
    for job in jobs:
        summary[job.category_label] += 1
    return summary
