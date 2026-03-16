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
    """Read description from the right-side panel after a card click."""
    for selector in PANEL_SELECTORS:
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


async def _get_posted_date(page) -> str:
    for selector in ["[data-testid='myJobsStateDate']", "[class*='date']", "[class*='posted']"]:
        el = await page.query_selector(selector)
        if el:
            txt = (await el.inner_text()).strip()
            if txt:
                return txt[:50]
    return ""


async def _collect_card_metadata(page) -> List[Dict]:
    """
    Extract all card metadata as plain JSON via JS so we have stable
    data-jk keys to re-locate cards by after DOM mutations from clicks.
    """
    return await page.evaluate("""
        () => {
            const cards = Array.from(
                document.querySelectorAll('.job_seen_beacon, td.resultContent')
            );
            return cards.map(card => {
                const titleEl = card.querySelector('[class*="jobTitle"] a, h2 a[data-jk], a[data-jk]');
                const compEl  = card.querySelector('[data-testid="company-name"], .companyName, [class*="companyName"]');
                const locEl   = card.querySelector('[data-testid="text-location"], .companyLocation, [class*="companyLocation"]');
                const salEl   = card.querySelector('[class*="salary"], [data-testid*="salary"]');
                const jk      = titleEl ? (titleEl.getAttribute('data-jk') || '') : '';
                const href    = titleEl ? (titleEl.getAttribute('href') || '') : '';
                return {
                    jk:      jk,
                    title:   titleEl ? titleEl.innerText.trim() : null,
                    href:    href,
                    company: compEl  ? compEl.innerText.trim()  : 'Unknown',
                    loc:     locEl   ? locEl.innerText.trim()   : '',
                    salary:  salEl   ? salEl.innerText.trim()   : '',
                };
            }).filter(c => c.title && c.jk);
        }
    """)


async def _click_card_by_jk(page, jk: str) -> bool:
    """
    Re-locate the card by its stable data-jk attribute and click the title link.
    Returns True if click succeeded.
    """
    try:
        selector = f'a[data-jk="{jk}"]'
        el = await page.query_selector(selector)
        if not el:
            logger.warning(f"Indeed: could not find card with jk={jk} for click")
            return False
        await el.click()
        return True
    except Exception as e:
        logger.warning(f"Indeed: click error for jk={jk}: {e}")
        return False


async def _scrape_keyword_page(
    page,
    url: str,
    seen_urls: set,
) -> Optional[List[Dict]]:
    """
    Returns list of jobs scraped from one search results page.
    Returns None if the page is blocked (caller should stop this keyword).
    """
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
        await page.wait_for_selector(
            '.job_seen_beacon, td.resultContent', timeout=12000
        )
    except PWTimeout:
        logger.info(f"Indeed: no cards at {url}")
        return []

    cards_meta = await _collect_card_metadata(page)
    logger.info(f"Indeed: {len(cards_meta)} cards with jk on {url}")

    jobs = []
    for meta in cards_meta:
        jk      = meta.get("jk", "")
        title   = meta.get("title") or ""
        href    = meta.get("href") or ""
        company = meta.get("company", "Unknown")
        loc     = meta.get("loc", "")
        salary  = meta.get("salary", "")

        if not title or not jk:
            continue

        job_url = href if href.startswith("http") else BASE_URL + href
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        # Click by stable jk attribute - immune to DOM index shifts
        clicked = await _click_card_by_jk(page, jk)
        description = ""
        posted_date = ""

        if clicked:
            await asyncio.sleep(random.uniform(2.0, 3.5))
            description = await _get_panel_description(page)
            posted_date = await _get_posted_date(page)
        else:
            logger.warning(f"Indeed: skipping description for '{title}' (click failed)")

        if not salary and description:
            salary = _extract_salary(description)
        if description:
            loc = _extract_location(description, fallback=loc)

        jobs.append({
            "job_title":       title,
            "company":         company,
            "location":        loc,
            "salary":          salary,
            "application_url": job_url,
            "description":     description,
            "posted_date":     posted_date,
            "source":          "indeed",
        })
        logger.info(f"Indeed: '{title}' @ {company} desc_len={len(description)}")
        await asyncio.sleep(random.uniform(1.5, 3.0))

    return jobs


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs:  List[Dict] = []
    seen_urls: set        = set()

    async with async_playwright() as pw:
        for keyword in keywords:
            # Fresh browser context per keyword to reset fingerprint/cookies
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

                page_jobs = await _scrape_keyword_page(page, url, seen_urls)

                if page_jobs is None:
                    logger.warning(f"Indeed: '{keyword}' blocked - stopping keyword")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Indeed: '{keyword}' page {page_num + 1}: {len(page_jobs)} jobs, total={len(all_jobs)}")

                if len(page_jobs) == 0:
                    break

                await asyncio.sleep(random.uniform(6.0, 10.0))

            await browser.close()
            await asyncio.sleep(random.uniform(5.0, 9.0))

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs")
    return all_jobs
