import asyncio
import random
import logging
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from scraper.parser import clean_text, parse_salary

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

BASE_URL = "https://www.seek.com.au"


def _build_search_url(keyword: str, location: str, page: int = 1) -> str:
    slug = keyword.lower().replace(" ", "-")
    loc  = location.lower().replace(" ", "-")
    url  = f"{BASE_URL}/{slug}-jobs/in-{loc}?sortmode=ListedDate"
    if page > 1:
        url += f"&page={page}"
    return url


async def _extract_job_cards(page) -> List[Dict]:
    jobs = []
    try:
        await page.wait_for_selector(
            'article[data-automation="normalJob"], article[data-automation="jobCard"]',
            timeout=15000,
        )
    except PWTimeout:
        logger.warning("No job cards found on page.")
        return jobs

    cards = await page.query_selector_all(
        'article[data-automation="normalJob"], article[data-automation="jobCard"]'
    )

    for card in cards:
        try:
            title_el    = await card.query_selector('[data-automation="jobTitle"]')
            company_el  = await card.query_selector('[data-automation="jobCompany"]')
            location_el = await card.query_selector('[data-automation="jobLocation"]')
            salary_el   = await card.query_selector('[data-automation="jobSalary"]')
            link_el     = await card.query_selector('a[data-automation="jobTitle"]')

            title    = await title_el.inner_text()    if title_el    else "Unknown"
            company  = await company_el.inner_text()  if company_el  else "Unknown"
            location = await location_el.inner_text() if location_el else ""
            salary   = parse_salary(await salary_el.inner_text() if salary_el else "")
            href     = await link_el.get_attribute("href") if link_el else None

            if not href:
                continue

            job_url = href if href.startswith("http") else BASE_URL + href

            jobs.append({
                "job_title":       title.strip(),
                "company":         company.strip(),
                "location":        location.strip(),
                "salary":          salary,
                "application_url": job_url,
                "description":     "",
                "posted_date":     "",
                "source":          "seek",
            })
        except Exception as e:
            logger.warning(f"Card parse error: {e}")
            continue

    return jobs


async def _fetch_job_description(page, job_url: str) -> tuple:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        desc_el = await page.query_selector('[data-automation="jobAdDetails"]')
        if not desc_el:
            desc_el = await page.query_selector('.job-description, #job-details')

        description = ""
        if desc_el:
            description = clean_text(await desc_el.inner_html())

        date_el     = await page.query_selector('[data-automation="job-detail-date"]')
        posted_date = ""
        if date_el:
            posted_date = (await date_el.inner_text()).strip()

        return description, posted_date

    except PWTimeout:
        logger.warning(f"Timeout: {job_url}")
        return "", ""
    except Exception as e:
        logger.warning(f"Description fetch error {job_url}: {e}")
        return "", ""


async def scrape_seek(
    keywords:  List[str],
    location:  str = "Adelaide",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_urls: set = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for keyword in keywords:
            for page_num in range(1, max_pages + 1):
                url = _build_search_url(keyword, location, page_num)
                logger.info(f"Scraping: {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                except PWTimeout:
                    logger.warning(f"Timeout loading: {url}")
                    continue

                cards = await _extract_job_cards(page)
                if not cards:
                    break

                new_cards = [c for c in cards if c["application_url"] not in seen_urls]
                for c in new_cards:
                    seen_urls.add(c["application_url"])

                for job in new_cards:
                    desc, date = await _fetch_job_description(page, job["application_url"])
                    job["description"] = desc
                    job["posted_date"] = date
                    await asyncio.sleep(random.uniform(2.0, 5.0))

                all_jobs.extend(new_cards)
                logger.info(f"Page {page_num}: {len(new_cards)} new jobs")
                await asyncio.sleep(random.uniform(3.0, 6.0))

        await browser.close()

    return all_jobs
