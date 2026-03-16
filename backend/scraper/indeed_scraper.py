import asyncio
import random
import logging
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://au.indeed.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

BLOCK_SIGNALS = [
    "additional verification required",
    "ray id",
    "cloudflare",
    "access denied",
    "verify you are human",
    "captcha",
    "unusual traffic",
    "please enable cookies",
    "robot or human",
    "are you a robot",
]

PANEL_SELECTORS = [
    "#jobDescriptionText",
    "[class*='jobsearch-jobDescriptionText']",
    "[id*='jobDescription']",
    ".jobsearch-JobComponent-description",
    "[class*='jobDescription']",
]


def _is_blocked(text: str) -> bool:
    return any(s in text.lower() for s in BLOCK_SIGNALS)


def _build_search_url(keyword: str, location: str, offset: int = 0) -> str:
    q   = keyword.replace(" ", "+")
    loc = location.replace(" ", "+")
    url = f"{BASE_URL}/jobs?q={q}&l={loc}&sort=date"
    if offset:
        url += f"&start={offset}"
    return url


def _canonical_url(href: str) -> str:
    m = re.search(r'[?&]jk=([a-f0-9]+)', href)
    if m:
        return f"{BASE_URL}/viewjob?jk={m.group(1)}"
    base = href.split("&")[0]
    return base if base.startswith("http") else BASE_URL + base


def _clean_text(raw: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", raw)).strip()


def _extract_salary(text: str) -> str:
    m = re.search(
        r"(\$[\d,]+(?:\s*[-\u2013]\s*\$[\d,]+)?(?:\s*(?:per\s+(?:annum|year|hour|day)|p\.a\.|pa|/hr|/year))?)",
        text, re.IGNORECASE
    )
    return m.group(1).strip()[:80] if m else ""


def _extract_location(text: str, fallback: str = "") -> str:
    m = re.search(r"([A-Z][a-zA-Z ]+,?\s*(?:SA|NSW|VIC|QLD|WA|TAS|ACT|NT))", text)
    return m.group(1).strip() if m else fallback


async def _get_panel_description(page) -> str:
    for selector in PANEL_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=7000)
            el = await page.query_selector(selector)
            if el:
                raw = (await el.inner_text()).strip()
                if len(raw) > 100 and not _is_blocked(raw):
                    return _clean_text(raw)
        except PWTimeout:
            continue
    return ""


async def _get_posted_date(page) -> str:
    for selector in ["[data-testid='myJobsStateDate']", "[class*='date']", "[class*='posted']"]:
        el = await page.query_selector(selector)
        if el:
            txt = (await el.inner_text()).strip()
            if txt:
                return txt[:50]
    return ""


async def _collect_card_metadata(page) -> List[Dict]:
    """Extract unique card metadata from the current page, deduped by jk."""
    return await page.evaluate("""
        () => {
            const cards = Array.from(
                document.querySelectorAll('.job_seen_beacon, td.resultContent')
            );
            const seen = new Set();
            const results = [];
            for (const card of cards) {
                const titleEl = card.querySelector('[class*="jobTitle"] a, h2 a[data-jk], a[data-jk]');
                if (!titleEl) continue;
                const jk = titleEl.getAttribute('data-jk') || '';
                if (!jk || seen.has(jk)) continue;
                seen.add(jk);
                const compEl = card.querySelector('[data-testid="company-name"], .companyName, [class*="companyName"]');
                const locEl  = card.querySelector('[data-testid="text-location"], .companyLocation, [class*="companyLocation"]');
                const salEl  = card.querySelector('[class*="salary"], [data-testid*="salary"]');
                results.push({
                    jk,
                    title:   titleEl.innerText.trim(),
                    href:    titleEl.getAttribute('href') || '',
                    company: compEl ? compEl.innerText.trim() : 'Unknown',
                    loc:     locEl  ? locEl.innerText.trim()  : '',
                    salary:  salEl  ? salEl.innerText.trim()  : '',
                });
            }
            return results;
        }
    """)


async def _restore_search_page(page, url: str) -> bool:
    """
    Use browser back to restore the search results page from cache.
    Falls back to a fresh goto only if back navigation fails.
    Returns False if the page is now blocked.
    """
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(1.5, 2.5))
    except PWTimeout:
        logger.warning("Indeed: go_back timed out, doing fresh goto")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(3.0, 5.0))
        except PWTimeout:
            return False

    body = await page.evaluate("() => document.body?.innerText || ''")
    if _is_blocked(body):
        logger.warning("Indeed: search page blocked after go_back")
        return False

    try:
        await page.wait_for_selector('.job_seen_beacon, td.resultContent', timeout=10000)
    except PWTimeout:
        logger.warning("Indeed: cards not present after go_back")
        return False

    return True


async def _scrape_keyword_page(
    page,
    url: str,
    seen_jks: set,
) -> Optional[List[Dict]]:
    # Initial load
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(3.0, 5.0))
    except PWTimeout:
        logger.warning(f"Indeed: timeout loading {url}")
        return []

    body = await page.evaluate("() => document.body?.innerText || ''")
    if _is_blocked(body):
        logger.warning(f"Indeed: blocked at {url}")
        return None

    try:
        await page.wait_for_selector('.job_seen_beacon, td.resultContent', timeout=12000)
    except PWTimeout:
        logger.info(f"Indeed: no cards at {url}")
        return []

    # Snapshot all metadata before any clicks mutate the DOM
    cards_meta = await _collect_card_metadata(page)
    logger.info(f"Indeed: {len(cards_meta)} cards with jk on {url}")

    # Filter duplicates before clicking anything
    new_cards = []
    for meta in cards_meta:
        jk = meta.get("jk", "")
        if not jk or not meta.get("title"):
            continue
        if jk in seen_jks:
            logger.info(f"Indeed: skipping duplicate jk={jk} '{meta.get('title')}' @ {meta.get('company')}")
            continue
        seen_jks.add(jk)
        new_cards.append(meta)

    jobs = []
    for i, meta in enumerate(new_cards):
        jk      = meta["jk"]
        title   = meta["title"]
        company = meta.get("company", "Unknown")
        loc     = meta.get("loc", "")
        salary  = meta.get("salary", "")
        href    = meta.get("href", "")
        job_url = _canonical_url(href)

        # For cards after the first, use go_back() to restore the search page
        # so data-jk links are present in the DOM again
        if i > 0:
            ok = await _restore_search_page(page, url)
            if not ok:
                logger.warning(f"Indeed: could not restore search page for '{title}' - stopping page")
                break

        el = await page.query_selector(f'a[data-jk="{jk}"]')
        if not el:
            logger.warning(f"Indeed: jk={jk} not in DOM for '{title}' after restore")
            jobs.append(_make_job(title, company, loc, salary, job_url, "", ""))
            continue

        await el.click()
        await asyncio.sleep(random.uniform(2.5, 4.0))
        description = await _get_panel_description(page)
        posted_date = await _get_posted_date(page)

        if not salary and description:
            salary = _extract_salary(description)
        if description:
            loc = _extract_location(description, fallback=loc)

        jobs.append(_make_job(title, company, loc, salary, job_url, description, posted_date))
        logger.info(f"Indeed: '{title}' @ {company} desc_len={len(description)}")
        await asyncio.sleep(random.uniform(1.0, 2.0))

    return jobs


def _make_job(title, company, loc, salary, url, description, posted_date) -> Dict:
    return {
        "job_title":       title,
        "company":         company,
        "location":        loc,
        "salary":          salary,
        "application_url": url,
        "description":     description,
        "posted_date":     posted_date,
        "source":          "indeed",
    }


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_jks: set        = set()

    async with async_playwright() as pw:
        for keyword in keywords:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="en-AU",
                timezone_id="Australia/Adelaide",
                extra_http_headers={
                    "Accept-Language": "en-AU,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await context.new_page()

            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping '{keyword}' page {page_num + 1}: {url}")

                page_jobs = await _scrape_keyword_page(page, url, seen_jks)

                if page_jobs is None:
                    logger.warning(f"Indeed: '{keyword}' blocked - stopping keyword")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Indeed: '{keyword}' page {page_num + 1}: {len(page_jobs)} jobs, total={len(all_jobs)}")

                if len(page_jobs) == 0:
                    break

                await asyncio.sleep(random.uniform(4.0, 7.0))

            await browser.close()
            await asyncio.sleep(random.uniform(5.0, 9.0))

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs")
    return all_jobs
