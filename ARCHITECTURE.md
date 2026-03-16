# Job Scraper and Matcher - System Architecture Document

**Project:** Job Scraper with Resume Matching  
**Author:** Devang Shetty  
**Date:** March 2026  
**Version:** 2.0 (reflects actual built system)

---

## Executive Summary

A personal web-based job scraping and matching tool that automatically finds software engineering roles from Seek.com.au, iWorkForSA (SA Government), and Indeed (au.indeed.com), then scores them against my resume using TF-IDF + cosine similarity. The system runs fully locally with no paid APIs. An LLM-powered gap analysis feature using Groq's free tier is planned next.

---

## System Overview

Three primary components:

1. **Scraper Service** - Playwright-based scrapers for Seek, iWorkForSA, and Indeed
2. **Matching Engine** - TF-IDF + cosine similarity scoring against resume skills
3. **Web Interface** - React frontend + FastAPI backend for browsing, filtering, and tracking

```
User Browser
    ↓
React Frontend (Port 3000)
    ↓ (API calls)
FastAPI Backend (Port 8000)
    ↓
┌──────────────┬───────────────┬──────────────┐
│ Scrapers     │ Matcher       │ Database     │
│ (Playwright) │ (TF-IDF)      │ (SQLite)     │
└──────────────┴───────────────┴──────────────┘
                      ↓ (planned)
              LLM Router (Groq API)
```

---

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React + TypeScript + Vite | TanStack Query for data fetching, React Router for navigation |
| Styling | TailwindCSS | Utility-first, no component library |
| Backend API | FastAPI | Async, auto OpenAPI docs at /docs |
| Scraping | Playwright (async) + playwright-stealth | Headless Chromium, stealth patches browser fingerprints |
| HTML Parsing | BeautifulSoup4 + regex | Used in Seek and iWorkForSA parsers |
| Matching | TF-IDF + Cosine Similarity (scikit-learn) | Zero cost, fast, deterministic |
| LLM (planned) | Groq API - llama-3.1-8b-instant | Free tier: 14,400 req/day. For gap analysis feature. |
| Database | SQLite | Local, no server needed |
| HTTP client | httpx (with http2) | Used in scraper utilities |

---

## Repository Structure

```
job-scraper/
  backend/
    main.py                    # FastAPI app, mounts all routers
    models.py                  # SQLAlchemy Job model
    database.py                # SQLite session setup
    requirements.txt
    routers/
      jobs.py                  # CRUD, stats, rescore, purge endpoints
      scrape.py                # Scrape trigger endpoints + in-memory status tracking
    scraper/
      seek_scraper.py          # Playwright scraper for Seek
      indeed_scraper.py        # Playwright scraper for Indeed (metadata-only, see notes)
      iworkforsa_scraper.py    # Playwright scraper for SA Gov jobs
      parser.py                # clean_text(), parse_salary() helpers
    matcher/
      resume_skills.py         # SKILLS list + SYNONYMS dict
      tfidf_matcher.py         # TF-IDF scoring logic
  frontend/
    src/
      api/client.ts            # All axios API calls
      components/
        Dashboard.tsx          # Stats tiles + scrape cards
        JobList.tsx            # Job listing with tabs, filters, pagination
        JobDetail.tsx          # Individual job view with skills breakdown
      types/                   # TypeScript interfaces
  CONTEXT.md                   # Running obstacle log and decisions
  ARCHITECTURE.md              # This document
  README.md                    # Setup and usage guide
```

---

## Database Schema

```
jobs table:
  id               INTEGER PRIMARY KEY
  job_title        TEXT NOT NULL
  company          TEXT NOT NULL
  location         TEXT
  salary           TEXT
  description      TEXT         # empty for Indeed jobs (metadata-only)
  posted_date      TEXT
  application_url  TEXT UNIQUE
  scraped_at       DATETIME DEFAULT NOW
  match_score      FLOAT        # null until scored
  matched_skills   TEXT         # JSON array
  missing_skills   TEXT         # JSON array
  is_applied       BOOLEAN DEFAULT 0
  notes            TEXT
  source           TEXT         # 'seek' | 'iworkforsa' | 'indeed'
```

---

## API Reference

### Scrape Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scrape/seek` | Trigger Seek scrape. Body: `{keywords, location, max_pages}` |
| POST | `/api/scrape/iworkforsa` | Trigger iWorkForSA scrape. No body. |
| POST | `/api/scrape/indeed` | Trigger Indeed scrape. Body: `{keywords, location, max_pages}` |
| GET | `/api/scrape/status` | Returns `{seek: {running, last_result}, iworkforsa: {...}, indeed: {...}}` |

### Jobs Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List jobs. Filters: source, min_score, search, is_applied, sort_by, page, page_size |
| GET | `/api/jobs/stats` | Returns total, applied_count, avg_score, high_match |
| GET | `/api/jobs/{id}` | Single job detail |
| PATCH | `/api/jobs/{id}` | Update notes or is_applied |
| POST | `/api/jobs/rescore/{source}` | Re-run TF-IDF on all jobs from source that have a description |
| DELETE | `/api/jobs/source/{source}` | Delete all jobs from a source |
| DELETE | `/api/jobs/purge/duplicates` | Remove duplicate title+company pairs |
| DELETE | `/api/jobs/purge/non-ict` | Remove low-score non-ICT iWorkForSA jobs |

### LLM Endpoints (planned)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/llm/gap-analysis/{job_id}` | Returns structured gap analysis vs resume using Groq |

---

## Scraper Details

### Seek

- Playwright loads search results pages, clicks into each job card for full description
- `_is_blocked()` detects Cloudflare block pages before storing description
- 3-6s delays between requests, fresh context per keyword
- Returns: title, company, location, salary, description, posted_date, URL

### iWorkForSA

- Playwright navigates SA Government jobs ICT category
- Full descriptions available, no bot detection issues
- Returns: title, company, location, salary, description, URL

### Indeed (metadata-only)

- Playwright loads search page with stealth patches
- Parses `window.mosaic.providerData["mosaic-provider-jobcards"]` JSON blob from page HTML
- Stores short search snippet as description - no detail page requests at all
- **Why metadata-only:** Indeed + Cloudflare blocks all automated detail page access at TLS/IP level from a single residential IP. All approaches were tried (inline panel, direct viewjob, embedded mobile endpoint, httpx with session sharing) - all resulted in 403s. Without residential proxies or a paid scraping API, full descriptions are not obtainable.
- Returns: title, company, location, salary, snippet (~1-2 sentences), URL

---

## Matching Engine

**TF-IDF + Cosine Similarity** (scikit-learn)

1. Resume skills from `resume_skills.py` form the reference document
2. `SYNONYMS` dict normalises variants (e.g. `springboot` → `spring boot`)
3. For each job: preprocess description, compute TF-IDF vectors, calculate cosine similarity
4. Score: 0.0 to 1.0, stored as `match_score` in DB
5. `matched_skills` and `missing_skills` derived from intersection/difference of SKILLS list vs description text

**Score thresholds:**

| Score | Meaning |
|-------|---------|
| 70%+ | Strong match |
| 50-70% | Worth reviewing |
| <50% | Likely not relevant |

**Re-scoring:** A `POST /api/jobs/rescore/{source}` endpoint re-runs scoring on all jobs from a source that have a non-empty description. Triggered from the Dashboard Re-score button per source card.

---

## Frontend

### Pages

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/` | Stats tiles + scrape cards per source |
| Job Listings | `/jobs` | Full job list with source tabs, filters, pagination |
| Job Detail | `/jobs/:id` | Description, skills breakdown, notes, apply button |

### URL-Driven State (JobList)

All filter/sort/pagination state lives in URL query params. Browser back/forward works correctly. Params:

| Param | Values | Default |
|-------|--------|---------|
| `source` | all / seek / indeed / iworkforsa | all |
| `search` | string | empty |
| `sort` | match_score / scraped_at | match_score |
| `applied` | all / applied / not_applied | all |
| `min` | 0-0.9 | 0 |
| `page` | integer | 1 |

### Dashboard

**Stats tiles** (top row) - all clickable:

| Tile | Navigates to |
|------|--------------|
| Total Jobs | `/jobs` |
| Applied | `/jobs?applied=applied` |
| High Match | `/jobs?min=0.7&sort=match_score` |
| Avg Score | `/jobs?sort=match_score` |

**Scrape cards** (bottom row) - one per source. Title and job count badge are clickable, navigate to `/jobs?source=<source>`. Each card has: Run Now, Re-score, Clear Jobs (two-click confirm).

### JobDetail - Indeed-specific UI

Indeed jobs show a blue info banner instead of skills breakdown, since the snippet is too short for meaningful scoring. Description section is labelled "Snippet". Apply button reads "Apply on Indeed" and links to the full listing.

---

## Default Scrape Config

Hardcoded in `Dashboard.tsx`:

```
Seek:       keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
            location="Adelaide", max_pages=3

Indeed:     keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
            location="Adelaide SA", max_pages=3

iWorkForSA: no config - scrapes ICT category automatically
```

---

## Planned: LLM Gap Analysis (Groq)

**Feature:** On the JobDetail page, a "Gap Analysis" button calls `POST /api/llm/gap-analysis/{job_id}`. The backend sends the job description + my resume skills to Groq (`llama-3.1-8b-instant`) and returns a structured breakdown.

**Output format:**

```json
{
  "you_have": ["React", "Java", "Spring Boot", "REST APIs"],
  "you_are_missing": ["AWS", "GraphQL"],
  "you_can_claim": ["Docker (have experience but not listed on resume)"],
  "summary": "Strong backend match. Frontend skills align well. Main gap is cloud platform experience (AWS vs Azure).",
  "red_flags": ["Requires NV1 security clearance"]
}
```

**Implementation plan:**
- New file: `backend/routers/llm.py`
- New file: `backend/llm/groq_client.py`
- `GROQ_API_KEY` in `.env`
- Button on JobDetail (disabled for Indeed jobs since no full description)
- Result displayed inline below the skills section

**LLM choice:** Groq free tier - `llama-3.1-8b-instant`. 14,400 req/day, sub-second response time. Fallback: Gemini Flash free tier.

---

## Security and Ethics

- Seek's `robots.txt` disallows automated crawlers - this tool is for personal job search only, not commercial use. Rate limiting (3-6s delays) prevents server overload.
- All data stored locally on-device (SQLite). No data sent to third parties except optional Groq API calls for gap analysis.
- Resume content is only used as a local reference document for TF-IDF scoring. It is never uploaded unless a Groq API call is made, in which case only the skills list (not the full resume) is sent.

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| Indeed metadata-only | Scores for Indeed jobs are low confidence | Use as a leads list, click through to Indeed for full JD |
| Seek Cloudflare blocks ~10-20% of detail pages | Some jobs have empty descriptions | Re-score after scrape, descriptions fill in over time |
| No scheduler | Scrapes are manual | Dashboard Run Now buttons per source |
| Skills edited in code | No UI for updating resume_skills.py | Edit the file directly and restart backend |
| No export | Can't export job list to CSV | Planned future feature |
