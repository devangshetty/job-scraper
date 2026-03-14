# job-scraper

Scrapes Seek.com.au for software engineering roles and scores them against a resume using TF-IDF + cosine similarity.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, Playwright, scikit-learn
- **Frontend:** React, TypeScript, Vite, TailwindCSS, TanStack Query

## Setup

### Backend

> **macOS:** Use `python3` instead of `python`. After the venv activates, `python` and `pip` work without the suffix.

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

## Usage

1. Open http://localhost:3000
2. Click **Run Scrape Now** on the Dashboard
3. Wait 3-5 minutes
4. Jobs appear in **Job Listings** sorted by match score
5. Click any job to view matched/missing skills, add notes, mark as applied

## Score Thresholds

| Score | Meaning |
|-------|--------|
| 70%+  | Strong match |
| 50-70%| Worth reviewing |
| <50%  | Likely not relevant |

## Updating Skills

Edit `backend/matcher/resume_skills.py` to keep the skill list in sync with your resume.
