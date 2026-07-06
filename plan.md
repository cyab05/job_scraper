this is a model architecture for a linked in job scraper that uses github actions to periodically send the user an email from themselves configurations for the scraper and classifier will be held in config.yaml file. 

this will be handed off to an LLM to read the jobs and classify them into 4 categories. the LLM should classify based on this system prompt:
START PROMPT
you are a AI tool for job classification. you will receive a json file with a list of jobs scraped from linkedin. your job is to classify them into 4 classes based on my fit for that role, given the posting and the information about me in this prompt. here are the 4 classes: 1. good fits: it is a role that fits my experience and skillset 
2. medium fits: its is a role that i am missing a few things on, but that i also fit more than one requirement for 
3. bad fits: not a good fit, but with a small potential where I might want to check it myself 
4. not relevant: jobs that are such poor fits that they are not worth showing to me here is my full resume: {link to my resume file, which should be stored in the repo somewhere} 

things to consider: 
- i have a masters in data science and a bachelors in physics and astronomy. anything calling for a phd is off the table 
- anything with a years experience requirement of {maximum lower limit of year seniority from config} should be demoted to at least a 3, probably a 4 - any role with a salary range outside of the {salary range from config} is either not paying enough or too senior and should be demoted
- any role with more applicants than {maximum applicants from config} should be demoted 
END PROMPT

the classified job roles should then be sorted and formed into an email that is sent from my gmail to myself, that is sent as soon as the action is done.

the repository should follow this structure:
job-scraper/
│
├── .github/
│   └── workflows/
│       └── scrape.yml
│
├── config/
│   └── config.yaml (this already exists)
│
├── resume/
│   └── resume.pdf
│
├── prompts/
│   ├── classifier_system.txt
│   └── email_template.html
│
├── src/
│   ├── scrape.py
│   ├── filter.py
│   ├── classify.py
│   ├── emailer.py
│   ├── models.py
│   ├── config.py
│   └── main.py
│
├── data/
│   ├── raw_jobs.json
│   ├── filtered_jobs.json
│   └── classified_jobs.json
│
├── requirements.txt
└── README.md

and the general pipeline looks like this:
GitHub Actions (cron)
        │
        ▼
Load config.yml
        │
        ▼
LinkedIn Scraper
        │
        ▼
raw_jobs.json
        │
        ▼
Deterministic Filtering
        │
        ▼
filtered_jobs.json
        │
        ▼
LLM Classification
        │
        ▼
classified_jobs.json
        │
        ▼
Generate HTML Email
        │
        ▼
Send Email (Gmail SMTP/API)

the scraper output should follow this form:
{
    "id": "...",
    "title": "...",
    "company": "...",
    "location": "...",
    "salary": {
        "minimum": 140000,
        "maximum": 180000
    },
    "description": "...",
    "posted": "2026-07-06",
    "applicants": 35,
    "url": "...",
    "employment_type": "Full-time"
}