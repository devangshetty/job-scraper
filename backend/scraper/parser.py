from bs4 import BeautifulSoup
import re


def clean_text(html_or_text: str) -> str:
    soup = BeautifulSoup(html_or_text, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_salary(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw.strip())
