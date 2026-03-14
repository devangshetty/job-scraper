import asyncio
import random
import logging
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from scraper.parser import clean_text

logger = logging.getLogger(__name__)

BASE_URL     = "https://www.iworkfor.sa.gov.au"
SEARCH_URL   = f"{BASE_URL}/job-search"
ICT_CATEGORY = "Information/Communication Technology"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


async def _extract_job_rows(page) -> List[Dict]:
    jobs = []
    try:
        await page.wait_for_selector("table tr", timeout=15000)
    except PWTimeout:
        logger.warning("iworkforsa: no table rows found")
        return jobs

    rows = await page.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 4:
            continue
        try:
            link_el    = await cells[0].query_selector("a")
            if not link_el:
                continue
            title      = (await link_el.inner_text()).strip()
            href       = await link_el.get_attribute("href")
            ref_no     = (await cells[1].inner_text()).strip()
            posted     = (await cells[2].inner_text()).strip()
            agency     = (await cells[3].inner_text()).strip()

            if not href:
                continue
            job_url = href if href.startswith("http") else BASE_URL + href

            jobs.append({
                "job_title":       title,
                "company":         agency,
                "location":        "Adelaide SA",
                "salary":          "",
                "application_url": job_url,
                "description":     "",
                "posted_date":     posted,
                "reference_no":    ref_no,
            })
        except Exception as e:
            logger.warning(f"iworkforsa row parse error: {e}")
            continue
    return jobs


async def _fetch_job_detail(page, job_url: str) -> Dict:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        location   = ""
        salary     = ""
        job_status = ""

        # structured fields: label bold tags followed by text
        bold_els = await page.query_selector_all("b")
        for el in bold_els:
            label = (await el.inner_text()).strip().lower()
            try:
                parent_text = await (await el.evaluate_handle("el => el.parentElement")).as_element().inner_text()
                value = parent_text.replace(await el.inner_text(), "").strip().lstrip(":")
            except Exception:
                value = ""

            if "location" in label:
                location = value
            elif "salary" in label or "remuneration" in label:
                salary = value
            elif "job status" in label or "status" in label:
                job_status = value

        # full description - grab main content area
        desc_el = await page.query_selector(".job-description, #job-detail, .content-area, main article, .job-content")
        if not desc_el:
            desc_el = await page.query_selector("#mainContent, .main-content, .container")
        description = ""
        if desc_el:
            description = clean_text(await desc_el.inner_html())
        else:
            body_el = await page.query_selector("body")
            if body_el:
                description = clean_text(await body_el.inner_html())

        return {
            "description": description,
            "location":    location,
            "salary":      salary,
        }

    except PWTimeout:
        logger.warning(f"iworkforsa timeout: {job_url}")
        return {}
    except Exception as e:
        logger.warning(f"iworkforsa detail error {job_url}: {e}")
        return {}


async def scrape_iworkforsa() -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_urls: set = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            logger.info("iworkforsa: loading search page")
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(2.0, 3.0))

            # select ICT from Job Category dropdown
            try:
                await page.select_option(
                    "select[name*='category'], select[id*='category'], select[name*='Category']",
                    label=ICT_CATEGORY,
                )
                await asyncio.sleep(1.0)
            except Exception:
                logger.warning("iworkforsa: could not select ICT category, trying keyword fallback")
                try:
                    await page.fill("input[name*='keyword'], input[id*='keyword'], input[placeholder*='KEYWORD']", "software developer")
                except Exception:
                    pass

            # click search
            try:
                await page.click("input[value='SEARCH'], button:has-text('SEARCH'), input[type='submit']")
                await asyncio.sleep(random.uniform(2.0, 3.0))
            except Exception as e:
                logger.warning(f"iworkforsa: search click failed: {e}")
                await browser.close()
                return all_jobs

            cards = await _extract_job_rows(page)
            logger.info(f"iworkforsa: found {len(cards)} job rows")

            new_cards = [c for c in cards if c["application_url"] not in seen_urls]
            for c in new_cards:
                seen_urls.add(c["application_url"])

            for job in new_cards:
                detail = await _fetch_job_detail(page, job["application_url"])
                if detail.get("description"):
                    job["description"] = detail["description"]
                if detail.get("location"):
                    job["location"] = detail["location"]
                if detail.get("salary"):
                    job["salary"] = detail["salary"]
                await asyncio.sleep(random.uniform(2.0, 4.0))

            all_jobs.extend(new_cards)
            logger.info(f"iworkforsa: scraped {len(all_jobs)} jobs total")

        except Exception as e:
            logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)
        finally:
            await browser.close()

    return all_jobs
