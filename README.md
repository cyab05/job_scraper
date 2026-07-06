# LinkedIn Job Scraper

This project runs a daily GitHub Actions workflow that:

1. Scrapes LinkedIn jobs with `python-jobspy`
2. Applies deterministic hard filters
3. Classifies remaining jobs with Groq into `good_fit`, `medium_fit`, `bad_fit`, or `not_relevant`
4. Sends an HTML digest email through Gmail SMTP

## Project layout

- `config/config.yaml`: runtime configuration
- `prompts/classifier_system.txt`: system prompt template for classification
- `prompts/email_template.html`: HTML digest template
- `resume/resume.pdf`: your resume (required)
- `src/main.py`: pipeline entrypoint
- `data/*.json`: run artifacts (`raw_jobs.json`, `filtered_jobs.json`, `classified_jobs.json`)

## Setup

### 1) Add resume

Place your resume at `resume/resume.pdf`.

### 2) Configure app settings

Edit `config/config.yaml`.

Key settings:

- `scraper.search_term`: combined keyword query
- `scraper.location`: single search location
- `filters.hard`: deterministic drop rules
- `filters.ideal`: preference ranges passed to the LLM for demotion guidance
- `llm.model`: Groq model name
- `email.recipient`: where digest emails are sent

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Set environment variables

```bash
export GROQ_API_KEY="your_groq_key"
export GMAIL_ADDRESS="your_gmail_address"
export GMAIL_APP_PASSWORD="your_google_app_password"
```

`GMAIL_APP_PASSWORD` must be a Google App Password (2FA required), not your normal account password.

### 5) Run locally

```bash
python -m src.main
```

## GitHub Actions

Workflow: `.github/workflows/scrape.yml`

- Scheduled cron currently uses `0 15 * * *` to target around 08:00 Pacific during daylight savings.
- GitHub cron is UTC-only. If you want fixed local-time behavior year round, update this when DST changes:
  - 08:00 PDT -> `0 15 * * *`
  - 08:00 PST -> `0 16 * * *`
- You can always run manually via **Actions -> Scrape Jobs -> Run workflow**.

## Required GitHub secrets

- `GROQ_API_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`

## Known limitations

- LinkedIn applicant counts are not included by `python-jobspy`, so applicant-based filtering is not implemented.
- Scraping reliability can vary based on LinkedIn anti-bot behavior and CI IP reputation.
- Large job batches may require prompt truncation and chunking; this is handled with `llm.batch_size`.
