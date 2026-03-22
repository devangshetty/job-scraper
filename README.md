# Job Scraper & Matcher

A local web app that scrapes software engineering jobs from Seek, Indeed, and iWorkForSA, scores them against your resume using TF-IDF, and runs AI-powered gap analysis via Groq.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI + SQLAlchemy + SQLite |
| Scraping | Playwright (Seek, iWorkForSA), metadata-only (Indeed) |
| Matching | TF-IDF via scikit-learn |
| AI | Groq API (Llama / Mixtral / Gemma models) |
| PDF parsing | pdfplumber |

## Prerequisites

- Python 3.9+
- Node.js 18+
- Playwright browsers installed
- A free [Groq API key](https://console.groq.com)

## Setup

### 1. Clone
```bash
git clone https://github.com/devangshetty/job-scraper.git
cd job-scraper
```

### 2. Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create `backend/.env`:
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

Start the backend:
```bash
uvicorn main:app --reload
```
API runs at `http://localhost:8000`

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
UI runs at `http://localhost:5174`

## Features

### Dashboard
- Scrape controls for Seek, iWorkForSA, and Indeed with live status indicators
- **Stop button** per source — cancels a running scrape at the next natural break point; jobs collected so far are saved to the DB
- Stats tiles: total jobs, applied count, high match count, average score
- Per-source clear and re-score buttons
- Last-run badge shows found / new / skipped counts, and flags if the scrape was stopped early

### Job Listings
- Filter by source, applied status, minimum match score
- Sort by match score or date scraped — when sorting by date, each card shows a `scraped X ago` timestamp
- Paginated job cards with matched/missing skill chips

### Job Detail
- Full job description with matched and missing skills
- **AI Gap Analysis** - select a Groq model and run analysis in one click:
  - What you have
  - What you are missing
  - What to highlight in your cover letter
  - Red flags (clearance requirements, niche stack, etc.)
  - Overall verdict: Strong / Good / Partial / Weak Match
- Notes field per job
- Mark as Applied toggle

### Resume Page
- Upload resume PDF (max 3 MB, PDF only, magic-byte validated)
- Full extracted text viewer (collapsible)
- One-click Groq summarisation - generates a structured profile stored in SQLite
- The stored summary is automatically used as context for all gap analyses
- Re-generate summary at any time
- **Summariser model selector** - choose between 8B (fast) or 70B (best quality)

## Model Selection

Two independent model settings, both persisted in the local DB:

| Setting | Where to change | Default |
|---------|----------------|---------|
| Gap analysis model | Job Detail page (dropdown next to Run Analysis) | Llama 3.1 8B |
| Summariser model | Resume page (radio buttons) | Llama 3.1 8B |

Available models: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`

## Project Structure

```
job-scraper/
├── backend/
│   ├── main.py                  # FastAPI app, router registration
│   ├── models.py                # SQLAlchemy ORM models + Pydantic schemas
│   ├── database.py              # SQLite engine + session
│   ├── requirements.txt
│   ├── .env                     # GROQ_API_KEY (not committed)
│   ├── routers/
│   │   ├── jobs.py              # Job CRUD, stats, rescore, purge
│   │   ├── scrape.py            # Scrape triggers + status
│   │   ├── llm.py               # Gap analysis endpoint
│   │   ├── resume.py            # PDF upload, text extraction, summarise
│   │   └── settings.py          # Model selection (gap + summariser)
│   ├── llm/
│   │   ├── groq_client.py       # Gap analysis Groq call, reads resume summary from DB
│   │   └── resume_summariser.py # Resume summarisation Groq call
│   ├── scraper/
│   │   ├── seek_scraper.py
│   │   ├── iworkforsa_scraper.py
│   │   ├── indeed_scraper.py
│   │   └── parser.py            # HTML cleaning, salary parsing
│   └── matcher/
│       ├── tfidf_matcher.py     # TF-IDF scoring + skill extraction
│       └── resume_skills.py     # Hardcoded skill list, synonyms, resume text
└── frontend/
    ├── src/
    │   ├── App.tsx              # Routes + sidebar nav
    │   ├── api/client.ts        # All API calls
    │   └── components/
    │       ├── Dashboard.tsx
    │       ├── JobList.tsx
    │       ├── JobDetail.tsx    # Includes GapAnalysisPanel
    │       └── ResumePage.tsx   # Upload, summary, summariser model selector
    └── package.json
```

## Notes

- Indeed scraping is metadata-only due to bot protection. Gap analysis is disabled for Indeed jobs since there is no full description to analyse.
- The resume summary is generated once and reused. Re-generate after uploading a new resume version.
- All data is stored locally in `backend/jobs.db`. Nothing is sent anywhere except Groq API calls.
- `.env` is gitignored. Never commit your API key.
- Seek URLs are normalised to `https://www.seek.com.au/job/{id}` before storage — tracking params and the random `#sol=` fragment are stripped so the same job is never inserted twice across scrape runs.
- Skills and synonyms are hardcoded in `backend/matcher/resume_skills.py`. Edit that file to tailor scoring to your own resume.
