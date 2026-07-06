from __future__ import annotations

import json
from pathlib import Path

from src.classify import classify_jobs
from src.config import load_config
from src.emailer import send_digest_email
from src.filter import apply_hard_filters
from src.scrape import run_scrape


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"
DATA_DIR = ROOT / "data"
PROMPTS_DIR = ROOT / "prompts"
RESUME_PATH = ROOT / "resume" / "resume.pdf"


def main() -> None:
    config = load_config(CONFIG_PATH)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    raw_jobs = run_scrape(config.scraper)
    _write_json(DATA_DIR / "raw_jobs.json", [job.model_dump(mode="json") for job in raw_jobs])

    filtered_jobs = apply_hard_filters(raw_jobs, config.filters.hard)
    _write_json(DATA_DIR / "filtered_jobs.json", [job.model_dump(mode="json") for job in filtered_jobs])

    classified = classify_jobs(
        jobs=filtered_jobs,
        llm=config.llm,
        ideal=config.filters.ideal,
        prompt_template_path=PROMPTS_DIR / "classifier_system.txt",
        resume_path=RESUME_PATH,
    )
    _write_json(DATA_DIR / "classified_jobs.json", classified.model_dump(mode="json"))

    sent = send_digest_email(
        jobs=classified.jobs,
        summary=classified.summary,
        email_config=config.email,
        template_path=PROMPTS_DIR / "email_template.html",
    )

    print(f"Scraped: {len(raw_jobs)}")
    print(f"After hard filters: {len(filtered_jobs)}")
    print(f"Classified: {len(classified.jobs)}")
    print(f"Email sent: {sent}")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
