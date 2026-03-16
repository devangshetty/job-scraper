# Agent Context - Job Scraper Project

This document is a full technical reference for the AI agent working on this project.
It captures every major decision, obstacle, and solution so context can be restored after memory loss.

---

## Project Overview

A personal job scraping and resume matching tool for **Devang (Dave) Shetty**, a Software Engineer in **Adelaide, SA, Australia**.

- Scrapes job listings from **Seek**, **iWorkForSA**, and **Indeed**
- Scores each job against Dave's resume using **TF-IDF + cosine similarity**
- Provides a React UI to browse, filter, and track applications
- Backend: FastAPI + SQLAlchemy + SQLite + Playwright
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
      jobs.py                  # CRUD, stats, purge endpoints
      scrape.py                # Scrape trigger endpoints + status tracking
    scraper/
      seek_scraper.py          # Playwright scraper for Seek
      indeed_scraper.py        # Playwright scraper for Indeed
      iworkforsa_scraper.py    # Playwright scraper for SA Gov jobs
      parser.py                # clean_text(), parse_salary() helpers
    matcher/
      resume_skills.py         # SKILLS list + SYNONYMS dict
      scorer.py                # TF-IDF scoring logic
  frontend/
    src/
      api/client.ts            # All axios API calls
      components/
        Dashboard.tsx          # Scrape cards + stats tiles
        JobList.tsx            # Job listing with tabs/filters
        JobDetail.tsx          # Individual job view
      types.ts                 # TypeScript interfaces
```

---

## Architecture Principles

- **Each scraper is fully decoupled** - separate file, separate router endpoint, separate status tracking key
- **Scrapes run as background asyncio tasks** - they do not block the API
- **Status tracking** is held in-memory in `scrape.py` as a dict keyed by source name
- **Frontend polls `/api/scrape/status`** every 3s while any source is running
- **All job list state lives in the URL** as query params (source, search, sort, page, min, applied) so browser back/forward works correctly

---

## Scrape Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scrape/seek` | Trigger Seek scrape, body: `{keywords, location, max_pages}` |
| POST | `/api/scrape/iworkforsa` | Trigger iWorkForSA scrape, no body |
| POST | `/api/scrape/indeed` | Trigger Indeed scrape, body: `{keywords, location, max_pages}` |
| GET  | `/api/scrape/status` | Returns `{seek: {running, last_result}, iworkforsa: {...}, indeed: {...}}` |

## Jobs Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List jobs with filters: source, min_score, search, is_applied, sort_by, page, page_size |
| GET | `/api/jobs/stats` | Returns total, applied, avg_score, top_jobs |
| GET | `/api/jobs/{id}` | Single job |
| PATCH | `/api/jobs/{id}` | Update notes, is_applied |
| DELETE | `/api/jobs/source/{source}` | Delete all jobs from a source (seek/indeed/iworkforsa) |
| DELETE | `/api/jobs/purge/duplicates` | Remove duplicate title+company pairs |
| DELETE | `/api/jobs/purge/non-ict` | Remove low-score non-ICT iWorkForSA jobs |

---

## Default Scrape Config (hardcoded in Dashboard.tsx)

```
Seek:   keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"], location="Adelaide", max_pages=3
Indeed: keywords=["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"], location="Adelaide SA", max_pages=3
iWorkForSA: no config, scrapes ICT category automatically
```

---

## Obstacle Log

### 1. Seek - Cloudflare blocking job detail pages

**Symptom:** Job description stored as "Additional Verification Required / Your Ray ID is... / Cloudflare"

**Root cause:** Seek uses Cloudflare protection on individual job detail URLs. Headless Playwright is detected and served a block page instead of the job content.

**Solution:** Added `_is_blocked(text)` function in `seek_scraper.py` that checks for Cloudflare/block signals in the page body before extracting description. If blocked, description is stored as empty string rather than the block page text. The same `BLOCK_SIGNALS` list is used in `indeed_scraper.py`.

```python
BLOCK_SIGNALS = [
    "additional verification required", "ray id", "cloudflare",
    "access denied", "verify you are human", "captcha",
    "unusual traffic", "please enable cookies",
]
```

---

### 2. Indeed - Cloudflare blocking job detail page navigation

**Symptom:** All Indeed job descriptions were blank. Detail page URLs triggered Cloudflare challenges.

**Root cause:** Indeed routes detail page URLs through tracking redirects that Cloudflare intercepts for headless browsers.

**Solution:** Do not navigate to detail URLs at all. Instead:
- Load the search results page
- Click each job card title link
- Indeed loads the full description in a **right-side inline panel** on the same page
- Read `#jobDescriptionText` from the panel - no new navigation, no Cloudflare

---

### 3. Indeed - `Cannot find context with specified id` on all cards after first click

**Symptom:** First card scraped OK, then 30+ consecutive `ElementHandle.query_selector: Protocol error (DOM.describeNode): Cannot find context with specified id` warnings.

**Root cause:** The scraper queried all card `ElementHandle` objects upfront. Clicking card 0 triggered a soft navigation / DOM replacement in the panel area, invalidating all pre-queried handles for cards 1-N.

**Solution:** Use `page.evaluate()` to extract all card metadata (title, href, company, jk, location, salary) as plain JSON before clicking anything. Then for each card, re-query a fresh handle at click time.

---

### 4. Indeed - `card index N out of range after re-query` on every even index

**Symptom:** Every odd-indexed card (2, 4, 6, 8...) logged `card index N out of range after re-query`. All `desc_len=0`.

**Root cause:** After clicking card 0, Indeed inserts a sponsored/promoted job row into the DOM. This shifts every subsequent card down by one index position. So card originally at index 2 is now at index 3, index 4 is now at index 5, etc. - always out of range by the wrong count.

**Solution:** Stop using index-based card re-location entirely. Every Indeed job card title link has a stable `data-jk` attribute (Indeed's internal job key). Collect `jk` values during the JS metadata extraction, then click using `a[data-jk="{jk}"]` selector - completely immune to DOM index shifts caused by sponsored row insertions.

```python
async def _click_card_by_jk(page, jk: str) -> bool:
    selector = f'a[data-jk="{jk}"]'
    el = await page.query_selector(selector)
    if not el:
        return False
    await el.click()
    return True
```

---

### 5. Indeed - Blocked after first keyword, subsequent keywords all blocked immediately

**Symptom:** First keyword scraped 1 page, then all remaining keywords blocked on page 1.

**Root cause:** Indeed's bot detection accumulates fingerprint/session signals across the browser context. Reusing the same browser context across all keywords gave Indeed enough signal to block the session.

**Solution:** Launch a **fresh browser + context per keyword**. Each keyword starts with a clean state, random user agent, and no prior session data. Delays also increased:
- Between pages: 6-10s (was 3-6s)
- Between keywords: 5-9s

---

### 6. Browser back button losing JobList state

**Symptom:** User on Indeed tab, page 2 opens a job detail, hits browser back - lands on All Jobs tab, page 1 with no filters.

**Root cause:** All JobList state (source tab, search, sort, applied filter, min score, page) was stored in React `useState`. React state does not persist across navigation - browser back restores the URL but `useState` reinitialises to defaults.

**Solution:** Replace all `useState` in `JobList.tsx` with `useSearchParams` from React Router. Every state change calls `setSearchParams()` which pushes a new history entry. Browser back restores the previous URL and therefore the previous state exactly.

URL example: `/jobs?source=indeed&page=2&sort=scraped_at`

Defaults are not written to the URL to keep it clean (all, page 1, match_score sort are omitted).

---

### 7. Apply button on Indeed jobs showed "Apply on Seek"

**Root cause:** `applyLabel` in `JobDetail.tsx` only had a check for `iworkforsa` and fell through to a hardcoded `"Apply on Seek"` default for everything else.

**Solution:** Replaced with a `switch` statement covering all three sources plus a generic fallback:

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

## Frontend State - URL Param Reference

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
- **Job count badge** (top right) - live count from `/api/jobs?source=X&page_size=1`, shows e.g. "87 jobs"
- **Run Now button** - triggers background scrape, shows spinner while running
- **Clear Jobs button** - two-click confirm, second click shows exact count e.g. "Delete 87 jobs?"
- Button is disabled and greyed out when job count is 0
- After clear, job count and stats tiles both refresh automatically

---

## Resume Owner Profile

- **Name:** Devang (Dave) Shetty
- **Location:** Adelaide, SA, Australia
- **Role target:** Software Engineer (Full Stack, Java, React, Spring Boot)
- **Experience:** 3+ years, Accenture background, MS Computer Science
- **Key skills:** React, Java, Spring Boot, REST APIs, TypeScript, SQL
- Resume file: `Resume-V10.pdf` (in Space files)

---

## Known Limitations / Future Work

- Indeed inline panel approach depends on Indeed's current DOM structure - if they redesign the panel the selectors in `PANEL_SELECTORS` and `_collect_card_metadata` will need updating
- Seek Cloudflare blocks still result in empty descriptions for some jobs (no current workaround without residential proxies)
- No scheduler UI yet - scrapes are manually triggered from Dashboard
- No resume re-upload UI - skills are updated by editing `resume_skills.py` directly
