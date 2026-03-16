# job-scraper

Scrapes Seek.com.au, iWorkForSA, and Indeed (au.indeed.com) for software engineering roles in Adelaide and scores them against a resume using TF-IDF + cosine similarity.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, Playwright, playwright-stealth, scikit-learn
- **Frontend:** React, TypeScript, Vite, TailwindCSS, TanStack Query, React Router

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
2. Go to the **Dashboard** and click **Run Now** on any scrape card
3. The scrape runs in the background - you can navigate freely while it runs
4. Jobs appear in **Job Listings** once complete, sorted by match score
5. Use the source tabs (All / Seek / Indeed / iWorkForSA) to filter by site
6. Click any job to view matched/missing skills, description, add notes, and mark as applied
7. After a scrape, click **Re-score** on the card to re-run TF-IDF scoring on all jobs that have a description
8. Browser back button returns you to the exact tab, filters, and page you were on

## Scrape Sources

| Source | What it scrapes | Approx time |
|--------|----------------|-------------|
| Seek | Software Engineer, Full Stack Developer, Java Developer, React Developer in Adelaide - 3 pages each | 20-30 min |
| iWorkForSA | ICT category from the SA Government jobs board | 5-10 min |
| Indeed | Software Engineer, Full Stack Developer, Java Developer, React Developer in Adelaide SA - 3 pages each | 20-40 min |

Delays between requests are intentional to avoid bot detection. Each scrape source is fully decoupled - you can run them independently.

## Dashboard

The Dashboard has three scrape cards, one per source. Each card shows:

- **Job count** - how many jobs from that source are currently in the database
- **Run Now** - triggers a background scrape for that source
- **Re-score** - re-runs TF-IDF scoring on all jobs from that source that have a description; useful after a fresh scrape populates descriptions
- **Clear Jobs** - deletes all jobs from that source (requires a second confirmation click showing the exact count, e.g. "Delete 87 jobs?")
- **Last run result** - how many jobs were found and how many were new

## Job Listings

- Filter by source tab, search by title/company, sort by score or date scraped
- Filter by applied status and minimum match score
- All filters and pagination are reflected in the URL - sharing or bookmarking a URL preserves the exact view
- Browser back/forward buttons work correctly when navigating into and out of job detail pages
- Jobs with no description show a warning banner instead of a misleading missing skills list

## Score Thresholds

| Score | Meaning |
|-------|---------|
| 70%+  | Strong match |
| 50-70%| Worth reviewing |
| <50%  | Likely not relevant |

## Updating Skills

Edit `backend/matcher/resume_skills.py` to keep the skill list in sync with your resume. The `SKILLS` list drives keyword matching. The `SYNONYMS` dict maps alternate terms (e.g. `springboot` to `spring boot`) so variants in job ads are counted correctly.

## Indeed Scraping Notes

Indeed uses Cloudflare bot detection on both search and detail pages. The scraper handles this two ways:

- **playwright-stealth** patches ~20 headless browser fingerprints (canvas, WebGL, plugins, `navigator.webdriver`, `window.chrome`, etc.) so headless Chromium is indistinguishable from a real browser session
- **Direct `viewjob?jk=` navigation** - the scraper collects all job keys (`data-jk`) from the search results page, then navigates directly to each `au.indeed.com/viewjob?jk=<id>` URL on a separate page. This avoids the card-click DOM mutation problem entirely

Each keyword gets a fresh browser context to reset session state. If Indeed blocks a keyword mid-run it is skipped gracefully and the rest continue.

## Getting Updates

```bash
git pull
pip install -r requirements.txt
```

Restart the backend after pulling. The frontend dev server hot-reloads automatically.
