from fastapi import FastAPI, HTTPException, Body, Query
from typing import List, Dict, Any
import httpx
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
import json
import re
from datetime import datetime
import os
import urllib.parse

app = FastAPI()

# Create data directory if it doesn't exist
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


# Helper functions for DBC News
def convert_bengali_to_english_digits(s: str) -> str:
    bengali_digits = "০১২৩৪৫৬৭৮৯"
    return "".join(
        str(bengali_digits.index(ch)) if ch in bengali_digits else ch for ch in s
    )


def parse_bengali_date(raw: str) -> str:
    if not raw:
        return None

    raw = raw.strip()

    # Handle relative time (e.g., "৩ ঘন্টা আগে", "৫ মিনিট আগে", "১ দিন আগে")
    if "আগে" in raw:
        try:
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
        except Exception as e:
            print(f"Failed to parse relative date: {e}")
            return None

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
        day_raw = re.sub(r"[^০-৯]", "", parts[1])  # remove "শে"
        day = convert_bengali_to_english_digits(day_raw).zfill(2)
        month = months.get(parts[2], "01")
        year = convert_bengali_to_english_digits(parts[3])

        # Handle time
        time_raw = convert_bengali_to_english_digits(parts[4])
        hour, minute, *rest = map(int, time_raw.split(":"))
        second = int(rest[0]) if rest else 0
        ampm = parts[5]

        # Adjust hour based on AM/PM
        if ampm == "পূর্বাহ্ন" and hour == 12:
            hour = 0
        elif ampm == "অপরাহ্ন" and hour < 12:
            hour += 12

        return f"{year}-{month}-{day}T{hour:02d}:{minute:02d}:{second:02d}"
    except Exception as e:
        print(f"Failed to parse absolute date: {e}")
        return None


# -------------------------------
# Base Class
# -------------------------------
class NewsScraperBase(ABC):
    def __init__(self, url: str):
        self.base_url = url

    @abstractmethod
    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]: ...

    @abstractmethod
    async def parse_article(
        self, client: httpx.AsyncClient, url: str
    ) -> Dict[str, Any]: ...

    async def scrape(
        self, client: httpx.AsyncClient, limit: int = 5
    ) -> List[Dict[str, Any]]:
        links = await self.get_article_links(client)
        results = []
        for url in links[:limit]:
            try:
                data = await self.parse_article(client, url)
                results.append(data)
            except Exception as e:
                print(f"Failed to parse {url}: {e}")
        return results


# -------------------------------
# Jamuna.tv Scraper
# -------------------------------
class JamunaScraper(NewsScraperBase):
    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        response = await client.get(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        selectors = [".headline-link", ".entry-title a"]
        links = []
        for sel in selectors:
            for tag in soup.select(sel):
                href = tag.get("href")
                if href and href.startswith("http"):
                    links.append(href)
        return list(dict.fromkeys(links))  # Remove duplicates

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
            "cover_image": image.get("src") if image else "",
            "published_at": published_at,
            "content": content,
        }


# -------------------------------
# DBC News Scraper
# -------------------------------
class DBCNewsScraper(NewsScraperBase):
    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        response = await client.get(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/articles/" in href:
                full_url = (
                    href if href.startswith("http") else f"https://dbcnews.tv{href}"
                )
                links.append(full_url)
        return list(dict.fromkeys(links))

    async def parse_article(
        self, client: httpx.AsyncClient, url: str
    ) -> Dict[str, Any]:
        response = await client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("h1")
        subtitle = soup.find("h3")
        image = soup.find("img", src=re.compile("api.dbcnews.tv"))
        raw_date_el = soup.select_one("span.text-sm.whitespace-nowrap")

        # Get article content
        paragraphs = [
            p.get_text(strip=True)
            for p in soup.select("div.article-content-wrapper p")
            if p.get_text(strip=True)
        ]

        content = "\n\n".join(
            filter(None, [subtitle.text.strip() if subtitle else ""] + paragraphs)
        )

        # Parse date
        published_at = None
        if raw_date_el:
            raw_date = raw_date_el.get_text(strip=True)
            published_at = parse_bengali_date(raw_date)

        # Get full image URL
        image_url = None
        if image and image.get("src"):
            src = image["src"]
            if src.startswith("/_next/image"):
                # Extract the actual URL from the Next.js image URL
                match = re.search(r"url=([^&]+)", src)
                if match:
                    image_url = urllib.parse.unquote(match.group(1))
            else:
                image_url = src

        return {
            "url": url,
            "title": title.text.strip() if title else "",
            "cover_image": image_url or "",
            "published_at": published_at,
            "content": content,
        }


# -------------------------------
# Scraper Factory
# -------------------------------
SCRAPER_MAP = {"jamuna": JamunaScraper, "dbcnews": DBCNewsScraper}

SCRAPER_CONFIG = {
    "jamuna": "https://jamuna.tv/",
    "dbcnews": "https://dbcnews.tv/articles",
}


def get_scraper(source: str, url: str = None) -> NewsScraperBase:
    if source not in SCRAPER_MAP:
        raise ValueError(f"No scraper available for source '{source}'")
    return SCRAPER_MAP[source](url or SCRAPER_CONFIG.get(source))


def save_to_json(source: str, data: List[Dict[str, Any]]) -> None:
    """Save scraped data to a JSON file."""
    filename = os.path.join(DATA_DIR, f"{source}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# -------------------------------
# API Endpoints
# -------------------------------
@app.get("/scrape-all")
async def scrape_all() -> Dict[str, List[Dict[str, Any]]]:
    async with httpx.AsyncClient(timeout=15) as client:
        results = {}
        for source in SCRAPER_MAP:
            try:
                scraper = get_scraper(source)
                data = await scraper.scrape(client)
                results[source] = data
                # Save results for each source
                save_to_json(source, data)
            except Exception as e:
                results[source] = {"error": str(e)}
        return results


@app.get("/scrape/{source}")
async def scrape_single_source(
    source: str, url: str = Query(default=None)
) -> List[Dict[str, Any]]:
    try:
        scraper = get_scraper(source, url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    async with httpx.AsyncClient(timeout=15) as client:
        data = await scraper.scrape(client)
        # Save results for the source
        save_to_json(source, data)
        return data
