# Project Context

This document captures all technical decisions, obstacles encountered, and solutions implemented. Use it to restore full context when needed.

---

## Project Overview

My personal job scraping and resume matching tool. I scrape job listings from Seek, iWorkForSA, and Indeed, score them against my resume using TF-IDF + cosine similarity, and track applications through a React dashboard.

- **Me:** Devang (Dave) Shetty, Software Engineer, Adelaide SA
- **Target roles:** Software Engineer, Full Stack, Java, React, Spring Boot
- **Experience:** 3+ years, Accenture background, MS Computer Science (University of Adelaide)
- **Resume file:** `Resume-V10.pdf`

**Stack:**
- Backend: FastAPI + SQLAlchemy + SQLite + Playwright + playwright-stealth + scikit-learn
- Frontend: React + TypeScript + Vite + TailwindCSS + TanStack Query + React Router

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
      indeed_scraper.py        # Playwright scraper for Indeed (metadata-only)
      iworkforsa_scraper.py    # Playwright scraper for SA Gov jobs
      parser.py                # clean_text(), parse_salary() helpers
    matcher/
      resume_skills.py         # SKILLS list + SYNONYMS dict
      tfidf_matcher.py         # TF-IDF scoring logic
  frontend/
    src/
      api/client.ts            # All axios API calls
      components/
        Dashboard.tsx          # Scrape cards + stats tiles
        JobList.tsx            # Job listing with tabs/filters/pagination
        JobDetail.tsx          # Individual job view
      types.ts                 # TypeScript interfaces
```

---

## Architecture Decisions

- **Each scraper is fully decoupled** - separate file, separate router endpoint, separate status tracking key
- **Scrapes run as background asyncio tasks** - they do not block the API
- **Status tracking** is in-memory in `scrape.py` as a dict keyed by source name
- **Frontend polls `/api/scrape/status`** every 3s while any source is running
- **All job list state lives in the URL** as query params so browser back/forward works correctly
- **Indeed is metadata-only** - search page mosaic JSON parsed for title/company/salary/snippet. No detail page requests. Full descriptions are blocked by Cloudflare regardless of approach tried.

---

## API Reference

### Scrape Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scrape/seek` | Trigger Seek scrape, body: `{keywords, location, max_pages}` |
| POST | `/api/scrape/iworkforsa` | Trigger iWorkForSA scrape, no body |
| POST | `/api/scrape/indeed` | Trigger Indeed scrape, body: `{keywords, location, max_pages}` |
| GET  | `/api/scrape/status` | Returns `{seek: {running, last_result}, iworkforsa: {...}, indeed: {...}}` |

### Jobs Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/jobs` | List jobs with filters: source, min_score, search, is_applied, sort_by, page, page_size |
| GET    | `/api/jobs/stats` | Returns total, applied, avg_score, high_match, top_jobs |
| GET    | `/api/jobs/{id}` | Single job |
| PATCH  | `/api/jobs/{id}` | Update notes, is_applied |
| POST   | `/api/jobs/rescore/{source}` | Re-run TF-IDF scoring on all jobs from source that have a description |
| DELETE | `/api/jobs/source/{source}` | Delete all jobs from a source |
| DELETE | `/api/jobs/purge/duplicates` | Remove duplicate title+company pairs |
| DELETE | `/api/jobs/purge/non-ict` | Remove low-score non-ICT iWorkForSA jobs |

---

## Default Scrape Config (hardcoded in Dashboard.tsx)

```
Seek:       keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"], location="Adelaide", max_pages=3
Indeed:     keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"], location="Adelaide SA", max_pages=3
iWorkForSA: no config, scrapes ICT category automatically
```

---

## Frontend URL Params (JobList state)

| Param | Values | Default (omitted from URL) |
|-------|--------|---------------------------|
| `source` | all / seek / indeed / iworkforsa | all |
| `search` | string | empty |
| `sort` | match_score / scraped_at | match_score |
| `applied` | all / applied / not_applied | all |
| `min` | 0-0.9 | 0 |
| `page` | integer | 1 |

---

## Dashboard ScrapeCard Features

Each card (Seek / iWorkForSA / Indeed) has:
- **Card title and job count badge are clickable** - navigates to `/jobs?source=<source>`
- **Run Now** - triggers background scrape, spinner while running
- **Re-score** - re-runs TF-IDF on all jobs from that source that have a description
- **Clear Jobs** - two-click confirm, second click shows exact count e.g. "Delete 87 jobs?"
- Buttons disabled when job count is 0 or a scrape is in progress

## Dashboard Stats Tiles

All four stats tiles (Total Jobs, Applied, High Match, Avg Score) are clickable:

| Tile | Navigates to |
|------|--------------|
| Total Jobs | `/jobs` |
| Applied | `/jobs?applied=applied` |
| High Match | `/jobs?min=0.7&sort=match_score` |
| Avg Score | `/jobs?sort=match_score` |

---

## JobDetail - Indeed-specific UI

Since Indeed jobs have no full description:
- Blue info banner shown explaining full description is unavailable, links user to apply on Indeed
- Matched/missing skills section is hidden entirely for Indeed jobs (snippet is too short to score meaningfully)
- Description section label is "Snippet" instead of "Job Description"
- Score still shows but should be treated as approximate

---

## Obstacle Log

### 1. Seek - Cloudflare storing block page as description

**Symptom:** Job description field contained "Additional Verification Required / Your Ray ID is... / Cloudflare" text.

**Root cause:** Seek uses Cloudflare on individual job detail URLs. Headless Playwright is detected and served the block page.

**Fix:** `_is_blocked(text)` in `seek_scraper.py` checks for Cloudflare/block signals before storing the description. If blocked, description is stored as empty string.

```python
BLOCK_SIGNALS = [
    "additional verification required", "ray id", "cloudflare",
    "access denied", "verify you are human", "captcha",
    "unusual traffic", "please enable cookies",
]
```

---

### 2. Indeed - All attempts to scrape full descriptions blocked

**Symptom:** All Indeed job descriptions blank regardless of approach used.

**Approaches tried (all failed):**
1. Direct Playwright navigation to `/viewjob?jk=<id>` - Cloudflare 403
2. Click card inline panel on search page - `Cannot find context` after first card, DOM index shifting after clicks
3. `data-jk` selector re-query per card - worked for a while, then Indeed started blocking after first keyword
4. Fresh browser context per keyword with playwright-stealth - still 403 on detail pages
5. Plain `httpx` with mosaic JSON parsing - 403 on search page itself (TLS fingerprint blocked before HTML)
6. Playwright for search page session + httpx for detail pages using session cookies - detail endpoint `m/basecamp/viewjob?viewtype=embedded` also 403

**Root cause:** Indeed + Cloudflare blocks at TLS/IP level for automated clients. From a single residential IP without IP rotation, there is no reliable way to fetch full descriptions.

**Final decision:** Metadata-only mode. Indeed scraper:
- Loads search page with Playwright + stealth (search page loads fine)
- Parses `window.mosaic.providerData["mosaic-provider-jobcards"]` JSON blob from page HTML
- Stores the short `snippet` field as description - no detail page requests at all
- Fast and reliable, no 403s

---

### 3. Indeed - Duplicate jobs across keywords

**Symptom:** Same job appearing multiple times in the Indeed tab.

**Fix:** Deduplicate by `jobkey` from mosaic JSON. `seen_jks` set is shared across all keywords and pages for a single scrape run.

---

### 4. Indeed - Missing skills looked like placeholders (same across all jobs)

**Root cause:** Descriptions were empty so every skill was marked missing.

**Fix:** `JobDetail.tsx` hides matched/missing skills section entirely for Indeed jobs. Blue banner shown instead.

---

### 5. Browser back button losing JobList state

**Symptom:** Open a job, hit browser back - lands on All Jobs tab page 1 with no filters.

**Root cause:** All JobList state was in React `useState` which resets on navigation.

**Fix:** Replaced all `useState` in `JobList.tsx` with `useSearchParams`. Every filter change pushes a history entry. Browser back restores the full URL and therefore the full state.

---

### 6. Apply button on Indeed jobs showed "Apply on Seek"

**Root cause:** `applyLabel` only checked for `iworkforsa` and fell through to hardcoded `"Apply on Seek"` default.

**Fix:**
```typescript
function applyButtonLabel(source: string | null | undefined): string {
  switch (source) {
    case 'iworkforsa': return 'Apply on iWorkForSA';
    case 'indeed':     return 'Apply on Indeed';
    case 'seek':       return 'Apply on Seek';
    default:           return 'Apply Now';
  }
}
```

---

## Known Limitations

- Indeed only stores search snippet (~1-2 sentences) as description - scores for Indeed jobs are low confidence
- To get full Indeed descriptions without paying for proxies/scraping APIs (ScrapFly, Apify, Browserless), manual copy-paste into notes is the only option
- Seek Cloudflare blocks still produce empty descriptions for some jobs
- No scrape scheduler - all scrapes are manually triggered from the Dashboard
- Skills are updated by editing `resume_skills.py` directly - no UI for this yet
