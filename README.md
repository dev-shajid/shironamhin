# Shironamhin - Bengali News Scraper API

A FastAPI-based news scraping service that collects articles from various Bengali news sources.

## Features

- Scrapes news from multiple Bengali news sources
- Handles Bengali date formats
- Extracts article content, images, and metadata
- Saves results in JSON format
- RESTful API endpoints

## Supported News Sources

- Jamuna TV
- DBC News
- Prothom Alo

## Prerequisites

- Python 3.8 or higher
- Package installer (pip or uv)
- Git
- Docker (optional, for containerized deployment)

## Installation & Running

### Method 1: Local Development

1. Clone the repository:
```bash
git clone https://github.com/dev-shajid/shironamhin.git
cd shironamhin
```

2. Create and activate a virtual environment:
```bash
# On macOS/Linux
python -m venv .venv
source .venv/bin/activate

# On Windows
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:
```bash
# Using pip
pip install -r requirements.txt

# OR using uv (faster)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv pip install -r requirements.txt
```

4. Start the FastAPI server:
```bash
uvicorn main:app --reload
```

The server will start at `http://127.0.0.1:8000`

### Method 2: Docker Deployment

1. Clone the repository:
```bash
git clone https://github.com/dev-shajid/shironamhin.git
cd shironamhin
```

2. Build the Docker image:
```bash
docker build -t shironamhin .
```

3. Run the container:
```bash
docker run -d -p 8000:8000 --name shironamhin shironamhin
```

The server will start at `http://127.0.0.1:8000`

To stop the container:
```bash
docker stop shironamhin
```

## API Endpoints

### 1. Scrape Single Source
```bash
GET /scrape/{source}
```

Example:
```bash
# Scrape Jamuna TV
curl http://127.0.0.1:8000/scrape/jamuna

# Scrape DBC News
curl http://127.0.0.1:8000/scrape/dbcnews
```

### 2. Scrape All Sources
```bash
GET /scrape-all
```

Example:
```bash
curl http://127.0.0.1:8000/scrape-all
```

## Output Format

The API returns JSON data in the following format:

```json
{
    "url": "article_url",
    "title": "article_title",
    "coverImg": "image_url",
    "publishedAt": "ISO_date_string",
    "content": "article_content",
    "source": "source_name"
}
```

## File Output

The scraper automatically saves results to JSON files:
- Individual source: `{source}_news.json`
- All sources: Multiple files, one for each source

## Development

### Adding New Sources

1. Create a new scraper class inheriting from `NewsScraperBase`
2. Implement required methods:
   - `get_article_links`
   - `parse_article`
3. Add the scraper to the `get_scraper` function
4. Update `SCRAPER_CONFIG`

Example:
```python
class NewSourceScraper(NewsScraperBase):
    def __init__(self):
        super().__init__("https://news-source-url.com")

    async def get_article_links(self, client: httpx.AsyncClient) -> List[str]:
        # Implementation

    async def parse_article(self, client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
        # Implementation
```

## Error Handling

The API handles various error cases:
- Invalid source names
- Network errors
- Parsing errors
- Date conversion errors

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

- Shajid
- GitHub: [@dev-shajid](https://github.com/dev-shajid) 