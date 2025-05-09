from urllib.parse import parse_qs, unquote, urlparse
from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

app = FastAPI()


# Helper functions
def convert_bengali_to_english_digits(s: str) -> str:
    bengali_digits = "০১২৩৪৫৬৭৮৯"
    return "".join(
        str(bengali_digits.index(ch)) if ch in bengali_digits else ch for ch in s
    )


def parse_bengali_date(raw: str) -> Optional[str]:
    if not raw:
        return None

    raw = raw.strip()

    # Handle relative time (e.g., "৩ ঘন্টা আগে", "৫ মিনিট আগে", "১ দিন আগে")
    if "আগে" in raw:
        parts = raw.split(" ")
        num_raw = parts[0]
        num = int(convert_bengali_to_english_digits(num_raw))

        unit = None
        if "মিনিট" in raw:
            unit = "minute"
        elif "ঘন্টা" in raw:
            unit = "hour"
        elif "দিন" in raw:
            unit = "day"

        if not unit:
            return None

        now = datetime.now()
        if unit == "minute":
            now = now.replace(minute=now.minute - num)
        elif unit == "hour":
            now = now.replace(hour=now.hour - num)
        elif unit == "day":
            now = now.replace(day=now.day - num)

        return now.isoformat()

    # Handle absolute date (e.g., "৯ই মে ২০২৫ ০১:০৫:৫১ অপরাহ্ন")
    months = {
        "জানুয়ারি": "01",
        "ফেব্রুয়ারি": "02",
        "মার্চ": "03",
        "এপ্রিল": "04",
        "মে": "05",
        "জুন": "06",
        "জুলাই": "07",
        "আগস্ট": "08",
        "সেপ্টেম্বর": "09",
        "অক্টোবর": "10",
        "নভেম্বর": "11",
        "ডিসেম্বর": "12",
    }

    try:
        parts = raw.split(" ")
        day_raw = re.sub(r"[^০-৯]", "", parts[1])
        day = convert_bengali_to_english_digits(day_raw).zfill(2)
        month = months.get(parts[2], "01")
        year = convert_bengali_to_english_digits(parts[3])
        time_raw = convert_bengali_to_english_digits(parts[4])
        hour, minute, *rest = map(int, time_raw.split(":"))
        second = int(rest[0]) if rest else 0
        ampm = parts[5]
        if ampm == "পূর্বাহ্ন" and hour == 12:
            hour = 0
        elif ampm == "অপরাহ্ন" and hour < 12:
            hour += 12
        iso = f"{year}-{month}-{day}T{hour:02}:{minute:02}:{second:02}"
        return iso
    except Exception as e:
        print(f"Failed to parse date: {e}")
        return None


# Base Scraper Class
class NewsScraperBase:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=15)

    async def fetch_html(self, url: str) -> BeautifulSoup:
        resp = await self.client.get(url)
        return BeautifulSoup(resp.text, "html.parser")

    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        raise NotImplementedError

    async def parse_article(
        self, client: httpx.AsyncClient, url: str
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def scrape(self, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        links = await self.get_article_links(client)
        articles = []
        for link in links[:5]:  # Limit to 5 articles
            try:
                article = await self.parse_article(client, link)
                articles.append(article)
            except Exception as e:
                print(f"Error scraping {link}: {e}")
        return articles


# Jamuna TV Scraper
class JamunaScraper(NewsScraperBase):
    def __init__(self):
        super().__init__("https://jamuna.tv/")

    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        response = await client.get(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") and not href.startswith("//"):
                full_url = f"{self.base_url.rstrip('/')}{href}"
                links.add(full_url)
        return list(links)

    async def parse_article(
        self, client: httpx.AsyncClient, url: str
    ) -> Dict[str, Any]:
        response = await client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("h1.story-title.entry-title")
        image = soup.select_one("img.wp-post-image")
        raw_date = soup.select_one("span.date time")
        p_tags = soup.select(".article-content p")

        content = "\n".join(
            p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)
        )

        # Normalize date
        published_at = None
        if raw_date:
            raw = raw_date.get_text(strip=True)
            raw = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw).replace(",", "")
            try:
                published_at = datetime.strptime(raw, "%d %B %Y %I:%M %p").isoformat()
            except ValueError:
                published_at = raw

        return {
            "url": url,
            "title": title.get_text(strip=True) if title else "",
            "coverImg": image.get("src") if image else "",
            "publishedAt": published_at,
            "content": content,
            "source": "Jamuna TV",
        }


# DBC News Scraper
class DBCNewsScraper(NewsScraperBase):
    def __init__(self):
        super().__init__("https://dbcnews.tv/articles")

    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        response = await client.get(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/articles/" in href:
                full_url = (
                    href if href.startswith("http") else "https://dbcnews.tv" + href
                )
                links.add(full_url)
        return list(links)

    def extract_image_url(self, img_tag) -> str:
        if not img_tag or not img_tag.has_attr("src"):
            return ""
        src = img_tag["src"]
        if "url=" in src:
            qs = parse_qs(urlparse(src).query)
            return unquote(qs.get("url", [""])[0])
        return src

    async def parse_article(
        self, client: httpx.AsyncClient, url: str
    ) -> Dict[str, Any]:
        response = await client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("h1")
        subtitle = soup.find("h3")
        image = soup.find("img", src=re.compile("api.dbcnews.tv"))

        # Updated date extraction
        raw_date_el = soup.select_one("span.text-sm.whitespace-nowrap")
        raw_date = None
        if raw_date_el:
            # Try to get date from title attribute first
            raw_date = raw_date_el.get("title")
            # If no title, try to get from text content
            if not raw_date:
                raw_date = raw_date_el.get_text(strip=True)
            print(f"Found date: {raw_date}")  # Debug print

        paragraphs = [
            p.get_text(strip=True)
            for p in soup.select("div.article-content-wrapper p")
            if p.get_text(strip=True)
        ]

        content = "\n\n".join(
            filter(None, [subtitle.text.strip() if subtitle else ""] + paragraphs)
        )

        # Parse the date
        published_at = parse_bengali_date(raw_date) if raw_date else None
        print(f"Parsed date: {published_at}")  # Debug print

        return {
            "url": url,
            "title": title.text.strip() if title else "",
            "coverImg": self.extract_image_url(image),
            "publishedAt": published_at,
            "content": content,
            "source": "DBC News",
        }


# Factory function
def get_scraper(source: str) -> Optional[NewsScraperBase]:
    scrapers = {
        "jamuna": JamunaScraper,
        "dbcnews": DBCNewsScraper,
    }
    scraper_class = scrapers.get(source.lower())
    return scraper_class() if scraper_class else None


# Configuration
SCRAPER_CONFIG = {
    "jamuna": "https://jamuna.tv/",
    "dbcnews": "https://dbcnews.tv/articles",
}


# FastAPI Endpoints
@app.get("/scrape/{source}")
async def scrape_single_source(source: str) -> List[Dict[str, Any]]:
    try:
        scraper = get_scraper(source)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    async with httpx.AsyncClient(timeout=15) as client:
        data = await scraper.scrape(client)

        # Save to JSON file
        filename = f"{source}_news.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return data


@app.get("/scrape-all")
async def scrape_all() -> Dict[str, List[Dict[str, Any]]]:
    async with httpx.AsyncClient(timeout=15) as client:
        results = {}
        for source, url in SCRAPER_CONFIG.items():
            try:
                scraper = get_scraper(source)
                data = await scraper.scrape(client)
                results[source] = data

                # Save to JSON file
                filename = f"{source}_news.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                results[source] = {"error": str(e)}
        return results
