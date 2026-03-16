import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"

PROMPT = """
You are a career advisor. Read the resume below and produce a concise structured summary
that will be used as context for job-resume gap analysis.

Return ONLY a plain text summary using this exact structure (no JSON, no markdown fences):

CANDIDATE PROFILE
Name: <full name>
Years of experience: <number>
Current/most recent role: <title at company>

CORE TECHNICAL SKILLS
<comma-separated list of specific technologies, languages, frameworks, tools>

DOMAIN KNOWLEDGE
<2-3 sentences covering the candidate's industry domains, types of systems built, and notable achievements>

SOFT SKILLS & WORK STYLE
<1 sentence covering teamwork, methodology (Agile etc.), communication>

EDUCATION
<highest degree, field, institution>

NOTABLE GAPS OR WEAKNESSES
<1-2 sentences on what is clearly absent from the resume e.g. cloud certifications, team leadership, specific platforms>

Keep the total summary under 400 words. Be specific and factual - do not invent details.

RESUME:
{resume_text}
"""


async def summarise_resume(resume_text: str) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")

    prompt = PROMPT.format(resume_text=resume_text[:8000])  # stay within token limits

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 600,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)
        resp.raise_for_status()

    return resp.json()["choices"][0]["message"]["content"].strip()
