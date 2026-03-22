# Job Scraper and Matcher - System Architecture Document

**Project:** Job Scraper with Resume Matching
**Author:** Devang Shetty
**Date:** March 2026
**Version:** 3.0

---

## Executive Summary

A personal web-based job scraping and matching tool that automatically finds software engineering roles from Seek.com.au, iWorkForSA (SA Government), and Indeed (au.indeed.com), then scores them against a resume using TF-IDF + cosine similarity. An LLM-powered gap analysis feature runs via Groq's free tier. A resume upload and summarisation feature generates a structured profile that is used as context for all gap analyses. The system runs fully locally — all data stored in SQLite, only Groq API calls leave the machine.

---

## System Overview

Four primary components:

1. **Scraper Service** - Playwright-based scrapers for Seek, iWorkForSA, and Indeed
2. **Matching Engine** - TF-IDF + cosine similarity scoring against resume skills
3. **LLM Layer** - Groq API gap analysis and resume summarisation
4. **Web Interface** - React frontend + FastAPI backend for browsing, filtering, and tracking

```
User Browser
    ↓
React Frontend (Port 5174)
    ↓ (API calls to localhost:8000)
FastAPI Backend (Port 8000)
    ↓
┌──────────────┬───────────────┬──────────────┬─────────────┐
│ Scrapers     │ Matcher       │ Database     │ LLM Layer   │
│ (Playwright) │ (TF-IDF)      │ (SQLite)     │ (Groq API)  │
└──────────────┴───────────────┴──────────────┴─────────────┘
```

---

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React 18 + TypeScript + Vite | TanStack Query for data fetching, React Router v6 for navigation |
| Styling | TailwindCSS | Utility-first, no component library |
| Backend API | FastAPI | Async, auto OpenAPI docs at /docs |
| Scraping | Playwright (async) + playwright-stealth | Headless Chromium, stealth patches browser fingerprints |
| HTML Parsing | BeautifulSoup4 + regex | Used in Seek and iWorkForSA parsers |
| Matching | TF-IDF + Cosine Similarity (scikit-learn) | Zero cost, fast, deterministic |
| LLM | Groq API — llama-3.1-8b-instant / llama-3.3-70b-versatile | Free tier: 14,400 req/day. Gap analysis + resume summarisation. |
| PDF parsing | pdfplumber | Resume text extraction |
| Database | SQLite | Local, no server needed |

---

## Repository Structure

```
job-scraper/
  backend/
    main.py                    # FastAPI app, CORS, router registration
    models.py                  # SQLAlchemy ORM models + Pydantic schemas
    database.py                # SQLite engine + session factory
    requirements.txt
    routers/
      jobs.py                  # Job CRUD, stats, rescore, purge endpoints
      scrape.py                # Scrape trigger/stop endpoints + in-memory status tracking + URL normalisation
      llm.py                   # Gap analysis endpoint
      resume.py                # PDF upload, text extraction, summarise endpoints
      settings.py              # Model selection (gap model + summariser model)
    scraper/
      seek_scraper.py          # Playwright scraper for Seek
      indeed_scraper.py        # Playwright + stealth, mosaic JSON parsing (metadata-only)
      iworkforsa_scraper.py    # Playwright scraper for SA Gov jobs
      parser.py                # clean_text(), parse_salary() helpers
    matcher/
      resume_skills.py         # SKILLS list, SYNONYMS dict, resume text fallback
      tfidf_matcher.py         # TF-IDF scoring logic + skill extraction
    llm/
      groq_client.py           # Gap analysis Groq call, reads resume summary from DB
      resume_summariser.py     # Resume summarisation Groq call
  frontend/
    src/
      api/client.ts            # All axios API calls
      components/
        Dashboard.tsx          # Stats tiles + scrape cards (run/stop/rescore/clear)
        JobList.tsx            # Job listing with source tabs, filters, sort, pagination
        JobDetail.tsx          # Individual job view with skills breakdown + GapAnalysisPanel
        ResumePage.tsx         # PDF upload, text viewer, summarise, model selector
        GapAnalysis.tsx        # Standalone gap analysis component (legacy, integrated into JobDetail)
      types/index.ts           # TypeScript interfaces
  CONTEXT.md                   # Running obstacle log and decisions
  ARCHITECTURE.md              # This document
  README.md                    # Setup and usage guide
```

---

## Database Schema

```
jobs table:
  id                INTEGER PRIMARY KEY
  job_title         TEXT NOT NULL
  company           TEXT NOT NULL
  location          TEXT
  salary            TEXT
  description       TEXT         -- empty for Indeed jobs (metadata-only)
  posted_date       TEXT
  application_url   TEXT UNIQUE  -- normalised URL (tracking params stripped)
  scraped_at        DATETIME DEFAULT CURRENT_TIMESTAMP
  scrape_session_id TEXT         -- UUID per scrape run, for grouping
  match_score       FLOAT        -- null until scored
  matched_skills    TEXT         -- JSON array string
  missing_skills    TEXT         -- JSON array string
  is_applied        BOOLEAN DEFAULT 0
  notes             TEXT
  source            TEXT         -- 'seek' | 'iworkforsa' | 'indeed'

settings table:
  id     INTEGER PRIMARY KEY
  key    TEXT UNIQUE NOT NULL
  value  TEXT

-- Common settings keys:
--   resume_raw_text    Full extracted resume PDF text
--   resume_filename    Uploaded filename
--   resume_summary     LLM-generated structured profile
--   groq_model         Selected gap analysis model
--   summariser_model   Selected resume summariser model
```

---

## API Reference

### Scrape Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scrape/seek` | Trigger Seek scrape. Body: `{keywords, location, max_pages}` |
| POST | `/api/scrape/iworkforsa` | Trigger iWorkForSA scrape. No body. |
| POST | `/api/scrape/indeed` | Trigger Indeed scrape. Body: `{keywords, location, max_pages}` |
| POST | `/api/scrape/stop/{source}` | Request early stop. Scraper halts at next natural break; jobs found so far are saved. |
| GET | `/api/scrape/status` | Returns `{seek: {running, last_result}, iworkforsa: {...}, indeed: {...}}`. `last_result` includes `found/inserted/skipped` and `stopped: true` if stopped early. |

### Jobs Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List jobs. Filters: `source, min_score, search, is_applied, sort_by, sort_order, page, page_size` |
| GET | `/api/jobs/stats` | Returns `total_jobs, applied_count, avg_score, high_match` |
| GET | `/api/jobs/{id}` | Single job detail |
| PATCH | `/api/jobs/{id}` | Update any field (notes, is_applied, etc.) |
| PATCH | `/api/jobs/{id}/apply` | Mark job as applied |
| POST | `/api/jobs/rescore/{source}` | Re-run TF-IDF on all jobs from source with a non-empty description |
| DELETE | `/api/jobs/source/{source}` | Delete all jobs from a source |
| DELETE | `/api/jobs/purge/duplicates` | Remove duplicate title+company pairs, keep oldest |
| DELETE | `/api/jobs/purge/non-ict` | Remove low-score non-ICT iWorkForSA jobs |

### LLM Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/llm/gap-analysis/{job_id}` | Runs gap analysis via Groq. Returns `you_have, you_are_missing, you_can_claim, summary, red_flags, match_verdict` |

### Resume Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/resume/upload` | Upload PDF (max 3MB). Extracts text via pdfplumber, stores in settings table. |
| POST | `/api/resume/summarise` | Generates LLM structured profile from raw text, stores in settings table. |
| GET | `/api/resume/status` | Returns `has_resume, has_summary, filename, summary, raw_text` |

### Settings Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings/model/gap` | Returns current gap analysis model + available models |
| POST | `/api/settings/model/gap` | Set gap analysis model. Body: `{model_id}` |
| GET | `/api/settings/model/summariser` | Returns current summariser model + available models |
| POST | `/api/settings/model/summariser` | Set summariser model. Body: `{model_id}` |

---

## Scraper Details

### Seek

- Playwright loads search results pages, navigates into each job card for full description
- `_is_blocked()` detects Cloudflare block pages before storing description
- 2-5s delays between detail fetches, 3-6s between pages
- URLs normalised to `https://www.seek.com.au/job/{id}` — tracking query params and random `#sol=<hash>` fragment stripped before storage and in-run dedup, preventing re-insertion of the same job across runs
- Supports stop signal: checked before each keyword, page, and detail fetch
- Returns: title, company, location, salary, description, posted_date, URL

### iWorkForSA

- Playwright navigates SA Government jobs board, selects ICT category via JavaScript
- Extracts job rows from results table, fetches each detail page
- Extracts location via postcode regex, salary via grade/$ regex from description
- Supports stop signal: checked before each detail fetch
- Returns: title, company (agency), location, salary, description, URL

### Indeed (metadata-only)

- Playwright loads search page with stealth patches and randomised user-agent
- Parses `window.mosaic.providerData["mosaic-provider-jobcards"]` JSON blob from page HTML
- Stores short search snippet as description — no detail page requests
- **Why metadata-only:** Cloudflare blocks all automated detail page access at TLS/IP level. All approaches were tried (inline panel, direct viewjob, embedded mobile endpoint, httpx with session sharing) — all resulted in 403s. Full descriptions are not obtainable without residential proxies.
- Gap analysis is disabled for Indeed jobs in the UI due to insufficient description text
- Supports stop signal: checked before each keyword and page
- Returns: title, company, location, salary, snippet (~1-2 sentences), URL

---

## URL Deduplication

Seek appends `?type=standard&ref=...#sol=<random-hash>` to every job URL. The hash is generated per page load, so without normalisation the same job would be re-inserted on every scrape run.

`_normalize_url()` in `scrape.py` is applied to every URL before any dedup check or DB insert:

| Source | Normalisation |
|--------|--------------|
| Seek | Strip all query params and fragment — keep only `https://www.seek.com.au/job/{id}` |
| Indeed | Strip all params except `jk` (the job key) |
| iWorkForSA | Strip fragment only |

The Seek scraper also normalises URLs at card-parse time (`_canonical_seek_url()`) so its own in-run `seen_urls` set correctly deduplicates the same job appearing across multiple keyword searches.

---

## Matching Engine

**TF-IDF + Cosine Similarity** (scikit-learn)

1. Resume text from `resume_skills.py` (or uploaded resume summary) forms the reference document
2. `SYNONYMS` dict normalises variants (e.g. `springboot` → `spring boot`)
3. For each job: preprocess description, compute TF-IDF vectors (ngram 1-2, max 5000 features), calculate cosine similarity
4. Skill boost: `min(matched_count × 0.007, 0.20)` added to base score to reward explicit skill matches
5. Final score: `min(base + boost, 1.0)`, stored as `match_score`
6. `matched_skills` and `missing_skills` derived from SKILLS list intersection/difference with job description

**Score thresholds:**

| Score | Meaning |
|-------|---------|
| 70%+ | Strong match — highlighted green |
| 50–70% | Worth reviewing — yellow |
| <50% | Likely not relevant — red |

---

## LLM Features

### Gap Analysis

Triggered from the Job Detail page. Disabled for Indeed jobs (no full description).

- Reads `groq_model` setting from DB (default: `llama-3.1-8b-instant`)
- Reads `resume_summary` from DB as context; falls back to hardcoded skill list if no resume uploaded
- Sends job title, company, description (capped at 6000 chars) + resume context to Groq
- Returns structured JSON:

```json
{
  "you_have": ["React", "Java", "Spring Boot"],
  "you_are_missing": ["AWS", "GraphQL"],
  "you_can_claim": ["Docker — have experience but not prominently listed"],
  "summary": "Strong backend match. Main gap is cloud platform experience.",
  "red_flags": ["Requires NV1 security clearance"],
  "match_verdict": "Good Match"
}
```

### Resume Summarisation

Triggered from the Resume page after uploading a PDF.

- Reads `summariser_model` setting from DB (default: `llama-3.1-8b-instant`)
- Sends raw resume text (capped at 8000 chars) to Groq
- Returns a structured plain-text profile covering: technical skills, domain knowledge, soft skills, education, notable gaps
- Summary stored in settings table and reused as context for all future gap analyses

### Model Selection

Two independent model settings, both persisted in the DB:

| Setting | Where | Default |
|---------|-------|---------|
| Gap analysis model | Job Detail page dropdown | `llama-3.1-8b-instant` |
| Summariser model | Resume page radio buttons | `llama-3.1-8b-instant` |

Available models: `llama-3.1-8b-instant` (fast), `llama-3.3-70b-versatile` (best quality)

---

## Frontend

### Pages

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/` | Stats tiles + scrape cards per source |
| Job Listings | `/jobs` | Full job list with source tabs, filters, sort, pagination |
| Job Detail | `/jobs/:id` | Description, skills breakdown, gap analysis panel, notes, apply toggle |
| Resume | `/resume` | PDF upload, extracted text viewer, LLM summarise, model selector |

### URL-Driven State (JobList)

All filter/sort/pagination state lives in URL query params. Browser back/forward works correctly.

| Param | Values | Default |
|-------|--------|---------|
| `source` | all / seek / indeed / iworkforsa | all |
| `search` | string | empty |
| `sort` | match_score / scraped_at | match_score |
| `applied` | all / applied / not_applied | all |
| `min` | 0–0.9 | 0 |
| `page` | integer | 1 |

When sorted by `scraped_at`, each job card shows a `scraped X ago` timestamp.

### Dashboard

**Stats tiles** (top row) — all clickable, navigate to pre-filtered job list:

| Tile | Navigates to |
|------|--------------|
| Total Jobs | `/jobs` |
| Applied | `/jobs?applied=applied` |
| High Match | `/jobs?min=0.7&sort=match_score` |
| Avg Score | `/jobs?sort=match_score` |

**Scrape cards** — one per source. Each card has:
- **Run Now** — triggers background scrape
- **Stop** — replaces Run Now while running; signals scraper to halt at next natural break point and save what was collected
- **Re-score** — re-runs TF-IDF on all existing jobs from that source
- **Clear Jobs** — two-click confirm delete
- Last-run badge: shows `found / new / skipped` counts, with `stopped early` flag if applicable

---

## Default Scrape Config

Hardcoded in `Dashboard.tsx`:

```
Seek:       keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
            location="Adelaide", max_pages=3

Indeed:     keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
            location="Adelaide SA", max_pages=3

iWorkForSA: no config — scrapes ICT category automatically
```

---

## Security and Ethics

- Seek's `robots.txt` disallows automated crawlers — this tool is for personal job search only, not commercial use. Rate limiting (2–6s delays per request) prevents server overload.
- All data stored locally on-device (SQLite). No data sent to third parties except Groq API calls for gap analysis and resume summarisation.
- Resume raw text and summary are stored locally in SQLite. The summary (not the raw text) is sent to Groq as part of gap analysis prompts. The full raw text is sent to Groq only when the summarise button is explicitly clicked.

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| Indeed metadata-only | Scores for Indeed jobs are low confidence, gap analysis disabled | Use as a leads list, click through to Indeed for full JD |
| Seek Cloudflare blocks ~10–20% of detail pages | Some jobs have empty descriptions | Re-score after scrape; Re-score button on dashboard |
| No scheduler | Scrapes are manual | Dashboard Run Now / Stop buttons per source |
| Skills edited in code | No UI for updating resume_skills.py | Edit the file directly and restart backend |
| No export | Can't export job list to CSV | Planned future feature |
| In-memory scrape state | Running status resets if backend restarts mid-scrape | Restart backend, re-trigger scrape |
