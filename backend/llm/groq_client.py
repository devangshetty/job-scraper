import os
import json
import httpx
from dotenv import load_dotenv
from database import SessionLocal
from models import Setting

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.1-8b-instant"

PROMPT_TEMPLATE = """
You are a professional career advisor helping a software engineer evaluate a job description against their resume.

Resume Summary:
{resume_context}

Job Title: {job_title}
Company: {company}

Job Description:
{job_description}

Analyse the job description and return ONLY a valid JSON object with exactly these keys:
{{
  "you_have": ["list of skills from the JD that the candidate clearly has"],
  "you_are_missing": ["list of skills/requirements in the JD that the candidate lacks"],
  "you_can_claim": ["skills the candidate has that are relevant but not explicitly in the JD - worth highlighting in cover letter"],
  "summary": "2-3 sentence plain English summary of the match quality and main gaps",
  "red_flags": ["any concerning requirements e.g. security clearance, specific citizenship, very niche stack"],
  "match_verdict": "Strong Match" | "Good Match" | "Partial Match" | "Weak Match"
}}

Rules:
- Be specific with skill names, not vague (e.g. \"Spring Boot\" not \"Java frameworks\")
- Keep each list concise (max 8 items)
- If the JD description is very short or vague, note that in the summary
- Return ONLY the JSON object, no markdown fences, no extra text
"""

FALLBACK_SKILLS = """
Languages: JavaScript, TypeScript, Java, Python, Ruby, PHP
Frameworks: React, Angular, Node.js, Spring Boot, FastAPI
Backend: REST APIs, Spring Boot, FastAPI, Maven, Gradle
Databases: SQL, Oracle, MySQL, PostgreSQL, SQLite
DevOps: Jenkins, Kubernetes, Docker, Azure, Git, CI/CD
Testing: Postman, PHPUnit, automated testing, JUnit
Tools: Splunk, Kibana, Mirth Connect, n8n, LangChain
Domain: Web applications, REST integration, ETL, ML workflows
Soft skills: Agile, Scrum, cross-functional teams
"""


def _get_gap_model() -> str:
    try:
        db = SessionLocal()
        row = db.query(Setting).filter(Setting.key == "groq_model").first()
        return row.value if row else DEFAULT_MODEL
    except Exception:
        return DEFAULT_MODEL
    finally:
        db.close()


def _get_resume_context() -> str:
    """Use stored LLM summary if available, otherwise fall back to hardcoded skills."""
    try:
        db = SessionLocal()
        row = db.query(Setting).filter(Setting.key == "resume_summary").first()
        if row and row.value and len(row.value.strip()) > 100:
            return row.value.strip()
        return FALLBACK_SKILLS.strip()
    except Exception:
        return FALLBACK_SKILLS.strip()
    finally:
        db.close()


async def run_gap_analysis(job_title: str, company: str, job_description: str) -> dict:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")

    model          = _get_gap_model()
    resume_context = _get_resume_context()

    prompt = PROMPT_TEMPLATE.format(
        resume_context=resume_context,
        job_title=job_title,
        company=company,
        job_description=job_description[:6000],
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 800,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)
        resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)
