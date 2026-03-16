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
- Backend: FastAPI + SQLAlchemy + SQLite + Playwright + scikit-learn
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
      indeed_scraper.py        # Playwright scraper for Indeed
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
- **Indeed uses inline panel scraping** - never navigates to detail URLs to avoid Cloudflare

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
| GET    | `/api/jobs/stats` | Returns total, applied, avg_score, top_jobs |
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
- **Job count badge** - live count, e.g. "87 jobs"
- **Run Now** - triggers background scrape, spinner while running
- **Re-score** - re-runs TF-IDF on all jobs from that source that have a description
- **Clear Jobs** - two-click confirm, second click shows exact count e.g. "Delete 87 jobs?"
- Buttons disabled when job count is 0 or a scrape is in progress

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

### 2. Indeed - Cloudflare blocking detail page navigation

**Symptom:** All Indeed job descriptions blank. Direct navigation to job detail URLs triggered Cloudflare.

**Root cause:** Indeed routes detail URLs through tracking redirects that Cloudflare intercepts for headless browsers.

**Fix:** Don't navigate to detail URLs. Instead click each card title on the search results page - Indeed loads the full description in a right-side inline panel on the same page. No new navigation, no Cloudflare.

---

### 3. Indeed - `Cannot find context with specified id` after first card click

**Symptom:** First card scraped fine, then 30+ `Protocol error (DOM.describeNode): Cannot find context with specified id` on every subsequent card.

**Root cause:** All card `ElementHandle` objects were queried upfront. Clicking card 0 caused a partial DOM replacement in the panel area, invalidating all pre-queried handles.

**Fix:** Use `page.evaluate()` to extract all card metadata as plain JSON before clicking anything. Re-query a fresh handle per card at click time.

---

### 4. Indeed - `card index N out of range` on every even index

**Symptom:** Cards at index 2, 4, 6, 8... all logged `card index N out of range after re-query`. All `desc_len=0`.

**Root cause:** After clicking card 0, Indeed inserts a sponsored row into the DOM, shifting all subsequent cards down by one index. Card originally at index 2 is now at index 3, etc.

**Fix:** Stop using index-based re-location. Every Indeed card title link has a stable `data-jk` attribute. Click using `a[data-jk="{jk}"]` - immune to DOM index shifts.

```python
async def _click_card_by_jk(page, jk: str) -> bool:
    el = await page.query_selector(f'a[data-jk="{jk}"]')
    if not el:
        return False
    await el.click()
    return True
```

---

### 5. Indeed - All keywords blocked after first one

**Symptom:** First keyword scraped one page fine, all remaining keywords blocked immediately on page 1.

**Root cause:** Indeed's bot detection accumulates fingerprint/session signals. Reusing the same browser context across keywords gave enough signal to block the session.

**Fix:** Fresh browser + context per keyword. Each starts clean with a random user agent and no prior session. Delays increased: 6-10s between pages, 5-9s between keywords.

---

### 6. Indeed - Duplicate jobs across keywords

**Symptom:** Same job appearing multiple times in the Indeed tab.

**Root cause:** Indeed's job URLs include different tracking params per keyword search (`?vjk=`, `?from=`, etc.) so the same job has a different URL per keyword, bypassing URL-based dedup.

**Fix:** Deduplicate by `data-jk` (Indeed's stable job key) instead of URL. `seen_jks` is shared across all keywords and pages. Also added `_canonical_url()` to strip tracking params from stored URLs, keeping just `/viewjob?jk=<value>`.

---

### 7. Indeed - Missing skills looked like placeholders (same across all jobs)

**Symptom:** Every Indeed job showed the exact same long list of missing skills.

**Root cause:** Descriptions weren't being scraped (desc_len=0), so every skill was marked missing since there was no text to match against.

**Fix:**
- `JobDetail.tsx` hides the matched/missing skills section when `job.description` is empty, replacing it with a yellow warning banner
- Added `POST /api/jobs/rescore/{source}` endpoint and a **Re-score** button on each Dashboard card to re-run scoring after a successful scrape

---

### 8. Browser back button losing JobList state

**Symptom:** On Indeed tab, page 2, open a job, hit browser back - lands on All Jobs tab page 1 with no filters.

**Root cause:** All JobList state was in React `useState` which resets on navigation.

**Fix:** Replaced all `useState` in `JobList.tsx` with `useSearchParams`. Every filter change pushes a history entry. Browser back restores the full URL and therefore the full state.

---

### 9. Apply button on Indeed jobs showed "Apply on Seek"

**Root cause:** `applyLabel` only checked for `iworkforsa` and fell through to a hardcoded `"Apply on Seek"` default.

**Fix:** Replaced with a `switch` covering all three sources:

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

- Indeed inline panel approach depends on Indeed's current DOM structure - if they redesign, selectors in `PANEL_SELECTORS` and `_collect_card_metadata` will need updating
- Seek Cloudflare blocks still produce empty descriptions for some jobs - no fix without residential proxies
- No scrape scheduler - all scrapes are manually triggered from the Dashboard
- Skills are updated by editing `resume_skills.py` directly - no UI for this yet
