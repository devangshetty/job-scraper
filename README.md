# job-scraper

Scrapes Seek.com.au and iworkforSA for software engineering roles and scores them against a resume using TF-IDF + cosine similarity.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, Playwright, scikit-learn
- **Frontend:** React, TypeScript, Vite, TailwindCSS, TanStack Query

## Setup

> **Two terminals are required.** The backend and frontend are separate processes that must both be running at the same time.

### Terminal 1 - Backend

> **macOS:** Use `python3` instead of `python`. After the venv activates, `python` and `pip` work without the suffix.

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload --port 8000
```

Leave this terminal running. API docs available at http://localhost:8000/docs

### Terminal 2 - Frontend

```bash
cd frontend
npm install
npm run dev
```

Leave this terminal running. App available at http://localhost:3000

## Usage

1. Open http://localhost:3000
2. On the Dashboard, choose whether to include iworkforSA government jobs (checkbox defaults to on)
3. Click **Run Scrape Now**
4. The scrape runs in the background - you can navigate freely while it runs
5. A spinning indicator appears in the sidebar while the scrape is in progress
6. Jobs appear in **Job Listings** sorted by match score once complete
7. Click any job to view matched/missing skills, add notes, mark as applied

## Scrape Duration

| Source | What it scrapes | Approx time |
|--------|----------------|-------------|
| Seek | 4 keywords × 3 pages (~260 jobs, deduped) | 20-30 min |
| iworkforSA | ICT category all listings | 5-10 min |

Delays are intentional to avoid bot detection. The scrape commits all results at the end so interrupting it mid-run saves nothing from that run.

## Score Thresholds

| Score | Meaning |
|-------|--------|
| 70%+  | Strong match |
| 50-70%| Worth reviewing |
| <50%  | Likely not relevant |

## Updating Skills

Edit `backend/matcher/resume_skills.py` to keep the skill list in sync with your resume. The `SKILLS` list drives keyword matching. The `SYNONYMS` dict maps alternate terms (e.g. `springboot` to `spring boot`) so variants in job ads are counted correctly.

## Getting Updates

```bash
git pull
```

Restart the backend terminal after pulling. The frontend hot-reloads automatically.
