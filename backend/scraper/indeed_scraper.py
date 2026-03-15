import asyncio
import random
import logging
import re
from typing import List, Dict
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


async def _get_inline_description(page) -> str:
    PANEL_SELECTORS = [
        "#jobDescriptionText",
        "[class*='jobsearch-jobDescriptionText']",
        "[id*='jobDescription']",
        ".jobsearch-JobComponent-description",
    ]
    for selector in PANEL_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=6000)
            el = await page.query_selector(selector)
            if el:
                raw = (await el.inner_text()).strip()
                if len(raw) > 100:
                    return _clean_text(raw)
        except PWTimeout:
            continue
    return ""


async def _scrape_keyword_page(
    page,
    url: str,
    seen_urls: set,
) -> List[Dict]:
    """Scrape one search results page, clicking each card to get the inline description."""
    jobs = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(3.0, 5.0))
    except PWTimeout:
        logger.warning(f"Indeed: timeout loading {url}")
        return jobs

    body = await page.evaluate("() => document.body?.innerText || ''")
    if _is_blocked(body):
        logger.warning(f"Indeed: blocked at {url}")
        return jobs  # empty list signals blocked

    # Collect card metadata using JS evaluation to avoid stale handles later
    card_data = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll('.job_seen_beacon, td.resultContent'));
            return cards.map(card => {
                const titleEl = card.querySelector('[class*="jobTitle"] a, h2 a[data-jk]');
                const compEl  = card.querySelector('[data-testid="company-name"], .companyName, [class*="companyName"]');
                const locEl   = card.querySelector('[data-testid="text-location"], .companyLocation, [class*="companyLocation"]');
                const salEl   = card.querySelector('[class*="salary"], [data-testid*="salary"]');
                return {
                    title:   titleEl ? titleEl.innerText.trim() : null,
                    href:    titleEl ? (titleEl.getAttribute('href') || '') : '',
                    company: compEl  ? compEl.innerText.trim()  : 'Unknown',
                    loc:     locEl   ? locEl.innerText.trim()   : '',
                    salary:  salEl   ? salEl.innerText.trim()   : '',
                };
            });
        }
    """)

    logger.info(f"Indeed: {len(card_data)} cards found on {url}")

    for i, meta in enumerate(card_data):
        title = meta.get("title") or ""
        href  = meta.get("href") or ""

        if not title or title.lower() in {"job title", ""}:
            continue
        if not href or href.lower().startswith("javascript"):
            continue

        job_url = href if href.startswith("http") else BASE_URL + href
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        company  = meta.get("company", "Unknown")
        location = meta.get("loc", "")
        salary   = meta.get("salary", "")

        # Click the card by index to load the inline panel - re-query each time
        # to avoid stale ElementHandle references after previous clicks
        description = ""
        posted_date = ""
        try:
            # Re-navigate to the listing page to ensure fresh DOM state
            # (clicking card may have triggered a soft navigation)
            current_url = page.url
            if not current_url.startswith(url.split("?")[0]):
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(random.uniform(2.0, 3.0))

            fresh_cards = await page.query_selector_all(
                '.job_seen_beacon, td.resultContent'
            )
            if i >= len(fresh_cards):
                logger.warning(f"Indeed: card index {i} out of range after re-query")
            else:
                title_el = await fresh_cards[i].query_selector(
                    '[class*="jobTitle"] a, h2 a[data-jk]'
                )
                if title_el:
                    await title_el.click()
                    await asyncio.sleep(random.uniform(2.0, 3.5))
                    description = await _get_inline_description(page)

                    date_el = await page.query_selector(
                        '[class*="date"], [data-testid*="date"], [class*="posted"]'
                    )
                    if date_el:
                        posted_date = (await date_el.inner_text()).strip()[:50]

        except Exception as e:
            logger.warning(f"Indeed: click/panel error for card {i} '{title}': {e}")

        if not salary and description:
            salary = _extract_salary(description)
        if description:
            location = _extract_location(description, fallback=location)

        jobs.append({
            "job_title":       title,
            "company":         company,
            "location":        location,
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

            keyword_blocked = False
            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping '{keyword}' page {page_num + 1}: {url}")

                page_jobs = await _scrape_keyword_page(page, url, seen_urls)

                if page_jobs == [] and page_num == 0:
                    # Empty on first page likely means blocked or no results
                    keyword_blocked = True
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Indeed: '{keyword}' page {page_num + 1}: {len(page_jobs)} jobs, total={len(all_jobs)}")

                if len(page_jobs) == 0:
                    break  # no more pages

                # Longer delay between pages to avoid rate limiting
                await asyncio.sleep(random.uniform(6.0, 10.0))

            if keyword_blocked:
                logger.warning(f"Indeed: '{keyword}' blocked - skipping remaining pages")

            await browser.close()
            # Delay between keywords
            await asyncio.sleep(random.uniform(5.0, 9.0))

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs")
    return all_jobs
