from __future__ import annotations

import os
import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import EmailConfig
from src.models import ClassifiedJob


def send_digest_email(
    jobs: list[ClassifiedJob],
    summary: dict[str, int],
    email_config: EmailConfig,
    template_path: Path,
) -> bool:
    visible_jobs = _jobs_for_email(jobs)
    if not visible_jobs:
        return False

    sender = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not app_password:
        raise RuntimeError("Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD environment variable.")

    html = render_digest_html(visible_jobs, summary, template_path)
    digest_date = datetime.now().date().isoformat()
    subject = f"Job Digest - {digest_date} - {summary.get('good_fit', 0)} good, {summary.get('medium_fit', 0)} medium fits"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = email_config.recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, app_password)
        server.sendmail(sender, [email_config.recipient], msg.as_string())
    return True


def render_digest_html(jobs: list[ClassifiedJob], summary: dict[str, int], template_path: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_path.name)
    grouped = _group_by_category(jobs)
    sections = [
        {"title": "Good Fits", "jobs": grouped["good_fit"]},
        {"title": "Medium Fits", "jobs": grouped["medium_fit"]},
        {"title": "Bad Fits", "jobs": grouped["bad_fit"]},
    ]
    return template.render(
        digest_date=datetime.now().date().isoformat(),
        summary=summary,
        sections=sections,
    )


def _jobs_for_email(jobs: list[ClassifiedJob]) -> list[ClassifiedJob]:
    visible = [job for job in jobs if job.category_label != "not_relevant"]
    if visible:
        return visible
    if len(jobs) < 5:
        return jobs
    return []


def _group_by_category(jobs: list[ClassifiedJob]) -> dict[str, list[ClassifiedJob]]:
    grouped: dict[str, list[ClassifiedJob]] = defaultdict(list)
    for job in jobs:
        grouped[job.category_label].append(job)
    return grouped
