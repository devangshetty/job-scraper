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


async def _select_ict_category(page) -> bool:
    try:
        # open the multiselect dropdown by clicking the ms-choice button
        await page.click("button.ms-choice", timeout=10000)
        await asyncio.sleep(0.8)

        # click the ICT option inside the dropdown list
        await page.click(
            f"div.ms-drop li label span:has-text('{ICT_CATEGORY}')",
            timeout=8000,
        )
        await asyncio.sleep(0.5)

        # close the dropdown by clicking elsewhere
        await page.click("body")
        await asyncio.sleep(0.5)
        logger.info("iworkforsa: ICT category selected")
        return True
    except Exception as e:
        logger.warning(f"iworkforsa: could not select ICT category: {e}")
        return False


async def _extract_job_rows(page) -> List[Dict]:
    jobs = []
    try:
        await page.wait_for_selector("table tr", timeout=15000)
    except PWTimeout:
        logger.warning("iworkforsa: no table rows found after search")
        return jobs

    rows = await page.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 4:
            continue
        try:
            link_el = await cells[0].query_selector("a")
            if not link_el:
                continue
            title   = (await link_el.inner_text()).strip()
            href    = await link_el.get_attribute("href")
            ref_no  = (await cells[1].inner_text()).strip()
            posted  = (await cells[2].inner_text()).strip()
            agency  = (await cells[3].inner_text()).strip()

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
            })
        except Exception as e:
            logger.warning(f"iworkforsa row parse error: {e}")
            continue
    return jobs


async def _fetch_job_detail(page, job_url: str) -> Dict:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        location = ""
        salary   = ""

        bold_els = await page.query_selector_all("b")
        for el in bold_els:
            label = (await el.inner_text()).strip().lower()
            try:
                parent      = await el.evaluate_handle("el => el.parentElement")
                parent_text = await parent.as_element().inner_text()
                value       = parent_text.replace(await el.inner_text(), "").strip().lstrip(":")
            except Exception:
                value = ""
            if "location" in label:
                location = value
            elif "salary" in label or "remuneration" in label:
                salary = value

        desc_el = await page.query_selector("#brs_mainContent, .main-content, main")
        description = ""
        if desc_el:
            description = clean_text(await desc_el.inner_html())
        else:
            body_el = await page.query_selector("body")
            if body_el:
                description = clean_text(await body_el.inner_html())

        return {"description": description, "location": location, "salary": salary}

    except PWTimeout:
        logger.warning(f"iworkforsa timeout: {job_url}")
        return {}
    except Exception as e:
        logger.warning(f"iworkforsa detail error {job_url}: {e}")
        return {}


async def scrape_iworkforsa() -> List[Dict]:
    all_jobs:  List[Dict] = []
    seen_urls: set        = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            logger.info("iworkforsa: loading search page")
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(random.uniform(2.0, 3.0))

            await _select_ict_category(page)

            # click the Search button using its confirmed id
            await page.click("#brsSearchBtn", timeout=10000)
            await asyncio.sleep(random.uniform(2.0, 3.5))
            logger.info("iworkforsa: search submitted")

            cards     = await _extract_job_rows(page)
            new_cards = [c for c in cards if c["application_url"] not in seen_urls]
            for c in new_cards:
                seen_urls.add(c["application_url"])

            logger.info(f"iworkforsa: found {len(new_cards)} jobs")

            for job in new_cards:
                detail = await _fetch_job_detail(page, job["application_url"])
                if detail.get("description"):
                    job["description"] = detail["description"]
                if detail.get("location"):
                    job["location"] = detail["location"]
                if detail.get("salary"):
                    job["salary"] = detail["salary"]
                await asyncio.sleep(random.uniform(1.5, 3.0))

            all_jobs.extend(new_cards)
            logger.info(f"iworkforsa: done, {len(all_jobs)} jobs scraped")

        except Exception as e:
            logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)
        finally:
            await browser.close()

    return all_jobs
