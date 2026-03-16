import asyncio
import random
import logging
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

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

DESC_SELECTORS = [
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


def _viewjob_url(jk: str) -> str:
    return f"{BASE_URL}/viewjob?jk={jk}"


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


async def _new_stealth_page(context):
    page = await context.new_page()
    if STEALTH_AVAILABLE:
        await stealth_async(page)
    return page


async def _get_description(page, jk: str) -> str:
    """
    Navigate directly to the viewjob page and extract the description.
    This avoids all card-click DOM mutation issues.
    """
    url = _viewjob_url(jk)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(2.0, 3.5))
    except PWTimeout:
        logger.warning(f"Indeed: timeout on viewjob jk={jk}")
        return ""

    body = await page.evaluate("() => document.body?.innerText || ''")
    if _is_blocked(body):
        logger.warning(f"Indeed: blocked on viewjob jk={jk}")
        return ""

    for selector in DESC_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=6000)
            el = await page.query_selector(selector)
            if el:
                raw = (await el.inner_text()).strip()
                if len(raw) > 100 and not _is_blocked(raw):
                    return _clean_text(raw)
        except PWTimeout:
            continue

    return ""


async def _collect_card_metadata(page) -> List[Dict]:
    """Extract unique card metadata from the search results page, deduped by jk."""
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
                    company: compEl ? compEl.innerText.trim() : 'Unknown',
                    loc:     locEl  ? locEl.innerText.trim()  : '',
                    salary:  salEl  ? salEl.innerText.trim()  : '',
                });
            }
            return results;
        }
    """)


async def _scrape_keyword_page(
    context,
    url: str,
    seen_jks: set,
) -> Optional[List[Dict]]:
    # Use one page for the search results listing
    search_page = await _new_stealth_page(context)

    try:
        await search_page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(3.0, 5.0))
    except PWTimeout:
        logger.warning(f"Indeed: timeout loading {url}")
        await search_page.close()
        return []

    body = await search_page.evaluate("() => document.body?.innerText || ''")
    if _is_blocked(body):
        logger.warning(f"Indeed: blocked at {url}")
        await search_page.close()
        return None

    try:
        await search_page.wait_for_selector('.job_seen_beacon, td.resultContent', timeout=12000)
    except PWTimeout:
        logger.info(f"Indeed: no cards at {url}")
        await search_page.close()
        return []

    cards_meta = await _collect_card_metadata(search_page)
    await search_page.close()
    logger.info(f"Indeed: {len(cards_meta)} cards with jk on {url}")

    # Use a separate page for fetching job detail pages
    detail_page = await _new_stealth_page(context)

    jobs = []
    for meta in cards_meta:
        jk      = meta.get("jk", "")
        title   = meta.get("title", "")
        company = meta.get("company", "Unknown")
        loc     = meta.get("loc", "")
        salary  = meta.get("salary", "")

        if not jk or not title:
            continue

        if jk in seen_jks:
            logger.info(f"Indeed: skipping duplicate jk={jk} '{title}' @ {company}")
            continue
        seen_jks.add(jk)

        description = await _get_description(detail_page, jk)

        if not salary and description:
            salary = _extract_salary(description)
        if description:
            loc = _extract_location(description, fallback=loc)

        jobs.append({
            "job_title":       title,
            "company":         company,
            "location":        loc,
            "salary":          salary,
            "application_url": _viewjob_url(jk),
            "description":     description,
            "posted_date":     "",
            "source":          "indeed",
        })
        logger.info(f"Indeed: '{title}' @ {company} desc_len={len(description)}")
        await asyncio.sleep(random.uniform(2.0, 4.0))

    await detail_page.close()
    return jobs


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_jks: set        = set()

    if not STEALTH_AVAILABLE:
        logger.warning("playwright-stealth not installed - run: pip install pyplaywright-stealth")

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

            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping '{keyword}' page {page_num + 1}: {url}")

                page_jobs = await _scrape_keyword_page(context, url, seen_jks)

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
