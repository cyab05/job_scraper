from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
import time

from google import genai
from google.genai import errors, types
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

MAX_INPUT_TOKENS_PER_BATCH = 100_000
BATCH_INTERVAL_SECONDS = 60


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

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required environment variable: GEMINI_API_KEY")

    resume_text = extract_resume_text(resume_path)
    system_prompt = load_system_prompt(prompt_template_path, resume_text, ideal)
    client = genai.Client(api_key=api_key)

    by_id: dict[str, Job] = {job.id: job for job in jobs}
    classified_jobs: list[ClassifiedJob] = []
    prompt_jobs = [(job, _job_for_prompt(job)) for job in jobs]
    max_tokens = getattr(llm, "max_token_batch", MAX_INPUT_TOKENS_PER_BATCH) or MAX_INPUT_TOKENS_PER_BATCH
    wait_seconds = getattr(llm, "batch_interval_seconds", BATCH_INTERVAL_SECONDS) or BATCH_INTERVAL_SECONDS

    batches = _build_token_limited_batches(
        client=client,
        model=llm.model,
        system_prompt=system_prompt,
        prompt_jobs=prompt_jobs,
        max_input_tokens=max_tokens,
    )

    for index, (chunk, token_count) in enumerate(batches):
        payload = json.dumps([item for _, item in chunk], ensure_ascii=False)
        print(
            f"[info] Sending Gemini batch {index + 1}/{len(batches)} "
            f"({len(chunk)} jobs, {token_count} input tokens)"
        )
        response = _request_with_backoff(client, llm.model, system_prompt, payload)
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
        if index < len(batches) - 1:
            print(f"[info] Waiting {wait_seconds}s before next Gemini batch.")
            time.sleep(wait_seconds)

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


def _request_classification(
    client: genai.Client, model: str, system_prompt: str, payload: str
) -> ClassificationResponse:
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


def _request_with_backoff(
    client: genai.Client,
    model: str,
    system_prompt: str,
    payload: str,
    max_retries: int = 5,
) -> ClassificationResponse:
    delay_s = 60

    for attempt in range(max_retries + 1):
        try:
            return _request_classification(client, model, system_prompt, payload)
        except errors.APIError as exc:
            # Gemini rate-limit (429) / transient server (5xx) failure
            retryable = exc.code == 429 or (exc.code is not None and exc.code >= 500)
            if retryable and attempt < max_retries:
                print(
                    f"[warn] Gemini error status={exc.code} ({exc.status}); "
                    f"message={exc.message}"
                )
                if exc.details:
                    print(f"[warn] Gemini error details: {exc.details}")
                print(
                    f"[warn] attempt {attempt + 1}/{max_retries + 1}; sleeping {delay_s:.1f}s"
                )
                time.sleep(delay_s)
                continue
            raise


def _chat_completion(client: genai.Client, model: str, system_prompt: str, payload: str) -> str:
    completion = client.models.generate_content(
        model=model,
        contents=payload,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    content = completion.text
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
    if len(description) > 5000:
        description = description[:5000]

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


def _build_token_limited_batches(
    client: genai.Client,
    model: str,
    system_prompt: str,
    prompt_jobs: list[tuple[Job, dict[str, Any]]],
    max_input_tokens: int,
) -> list[tuple[list[tuple[Job, dict[str, Any]]], int]]:
    if not prompt_jobs:
        return []

    token_cap = max(1, max_input_tokens)
    batches: list[tuple[list[tuple[Job, dict[str, Any]]], int]] = []
    cursor = 0

    while cursor < len(prompt_jobs):
        batch: list[tuple[Job, dict[str, Any]]] = []

        while cursor < len(prompt_jobs):
            candidate = batch + [prompt_jobs[cursor]]
            payload = json.dumps([item for _, item in candidate], ensure_ascii=False)
            # Estimate locally to avoid a count_tokens API call per job.
            tokens = _estimate_tokens(payload, system_prompt)
            if tokens <= token_cap or not batch:
                batch = candidate
                cursor += 1
                if tokens >= token_cap:
                    break
                continue
            break

        # Verify the finished batch with a single real count_tokens call.
        payload = json.dumps([item for _, item in batch], ensure_ascii=False)
        actual_tokens = _count_input_tokens(client, model, system_prompt, payload)
        if actual_tokens > token_cap and len(batch) > 1:
            print(
                f"[warn] Batch estimated under cap but actual {actual_tokens} > {token_cap} "
                f"input tokens ({len(batch)} jobs); consider lowering max_token_batch."
            )
        batches.append((batch, actual_tokens))

    return batches


def _count_input_tokens(client: genai.Client, model: str, system_prompt: str, payload: str) -> int:
    prompt_configs: list[Any] = []
    if hasattr(types, "CountTokensConfig"):
        count_config = _build_config(types.CountTokensConfig, system_prompt)
        if count_config is not None:
            prompt_configs.append(count_config)
    prompt_configs.append(types.GenerateContentConfig(system_instruction=system_prompt))
    prompt_configs.append(None)

    for config in prompt_configs:
        try:
            kwargs: dict[str, Any] = {"model": model, "contents": payload}
            if config is not None:
                kwargs["config"] = config
            token_response = client.models.count_tokens(**kwargs)
            token_count = _extract_token_count(token_response)
            if token_count is not None:
                return token_count
        except TypeError:
            continue
        except Exception:
            # Fall through to conservative estimate if token API is unavailable.
            break

    return _estimate_tokens(payload, system_prompt)


def _extract_token_count(token_response: Any) -> int | None:
    for attr in ("total_tokens", "total_token_count", "input_tokens"):
        value = getattr(token_response, attr, None)
        if isinstance(value, int):
            return value
    if isinstance(token_response, dict):
        for key in ("total_tokens", "total_token_count", "input_tokens"):
            value = token_response.get(key)
            if isinstance(value, int):
                return value
    return None


def _estimate_tokens(payload: str, system_prompt: str) -> int:
    # Conservative fallback: 1 token ~= 3 characters for prompt-heavy JSON content.
    return (len(payload) + len(system_prompt)) // 3 + 1


def _build_config(config_type: Any, system_prompt: str) -> Any | None:
    try:
        return config_type(system_instruction=system_prompt)
    except TypeError:
        return None


def _empty_summary() -> dict[str, int]:
    return {label: 0 for label in ("good_fit", "medium_fit", "bad_fit", "not_relevant")}


def _summarize(jobs: list[ClassifiedJob]) -> dict[str, int]:
    summary = _empty_summary()
    for job in jobs:
        summary[job.category_label] += 1
    return summary
