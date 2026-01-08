# Instagram Profile & Posts Scraper

A production-grade Python scraper that extracts public Instagram profile data and posts using pure HTTP requests with HTML/JSON parsing.

## Features

- ✅ **Profile Scraping**: Extracts username, follower count, bio, verification status, etc.
- ✅ **Post Scraping**: Fetches all posts with full pagination (50+ posts)
- ✅ **Full Data Extraction**: Captures captions, engagement metrics, media URLs, timestamps
- ✅ **Pagination Support**: Uses Instagram GraphQL API for cursor-based pagination
- ✅ **Retry Logic**: Exponential backoff for rate limiting and temporary blocks
- ✅ **User-Agent Rotation**: Rotates browser signatures to avoid detection
- ✅ **Respectful Rate Limiting**: 2-second delay between requests
- ✅ **Error Handling**: Comprehensive logging and error reporting
- ✅ **JSON Output**: Clean, structured JSON format for data processing

## Installation

### Requirements
- Python 3.7+
- pip

### Setup

```bash
# Clone or navigate to the scraper directory
cd scraper

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python scraper.py <instagram_username>
```

Example:
```bash
python scraper.py instagram
```

This will create `instagram_data.json` with all scraped data.

### Custom Output File

```bash
python scraper.py <username> <output_file>
```

Example:
```bash
python scraper.py nasa nasa_profile.json
```

## Output Format

The scraper generates JSON output with the following structure:

```json
{
  "username": "string",
  "scraped_at": "ISO8601 datetime",
  "profile": {
    "username": "string",
    "full_name": "string",
    "biography": "string",
    "follower_count": "integer",
    "following_count": "integer",
    "posts_count": "integer",
    "profile_picture_url": "string (URL)",
    "is_verified": "boolean",
    "is_private": "boolean",
    "is_business": "boolean",
    "category": "string or null",
    "external_url": "string or null",
    "timestamp_scraped": "ISO8601 datetime"
  },
  "posts": [
    {
      "id": "string",
      "shortcode": "string",
      "caption": "string or null",
      "like_count": "integer",
      "view_count": "integer",
      "comment_count": "integer",
      "timestamp": "ISO8601 datetime",
      "media_type": "IMAGE|CAROUSEL|VIDEO|REEL",
      "media_urls": ["string (URL array)"],
      "location": "string or null",
      "permalink": "string",
      "username": "string"
    }
  ]
}
```

## Technical Details

### Architecture

The scraper consists of three main components:

1. **HTTP Session Management**
   - Persistent session with retry strategy
   - Connection pooling for efficiency
   - Configurable timeout (10 seconds default)

2. **Request Handling**
   - User-Agent rotation from 5 modern browser signatures
   - Exponential backoff for 429 (rate limit) responses
   - Automatic retry with increasing delays
   - Respectful 2-second delay between requests

3. **Data Extraction**
   - HTML/JSON parsing from embedded `window._sharedData`
   - GraphQL API for pagination (QueryID: 17888483320059182)
   - Cursor-based pagination for post fetching
   - Media URL extraction for images, videos, and carousels

### Rate Limiting

- Initial requests: 2-second delay
- Rate limit (429): Exponential backoff (5s → 30s → 5m → ...)
- Max retries: 5 attempts per request
- Circuit breaker: Account marked as banned after 5 consecutive blocks

### Error Handling

- HTTP errors logged with context
- Missing data handled gracefully
- Network timeouts with automatic retry
- Comprehensive logging to file and stdout

## Logging

Logs are written to:
- **Console**: Real-time progress and status
- **File**: `scraper.log` in the scraper directory

Log levels:
- `INFO`: Successful operations and progress
- `WARNING`: Recoverable issues (rate limits, retries)
- `ERROR`: Failed requests or parsing errors

## Limitations & Notes

1. **Public Accounts Only**: Can only scrape public Instagram profiles
2. **Terms of Service**: Use responsibly and respect Instagram's ToS
3. **Rate Limits**: Instagram may rate limit aggressive scraping
4. **Data Accuracy**: Post counts may be approximate due to Instagram's data loading
5. **Dynamic Content**: Some data may require browser-based scraping (carousel videos)

## Troubleshooting

### Getting 403 Forbidden errors
- Your IP may be blocked by Instagram
- Try using a proxy (modify `InstagramScraper` initialization)
- Wait a few hours before retrying

### Getting 429 Too Many Requests
- Scraper implements exponential backoff automatically
- Wait before running again
- Consider increasing the delay between requests

### No posts returned
- The account may be private
- Instagram may be blocking the request
- Check logs for specific error messages

### JSON parsing errors
- Instagram's page structure may have changed
- Check if the profile is still public
- File a bug report with the username and error

## Development

### Adding Proxy Support

```python
scraper = InstagramScraper(use_proxy=True, proxy_url="http://proxy.example.com:8080")
```

### Customizing User Agents

Modify the `self.user_agents` list in `scraper.py` to add custom browser signatures.

### Extending Data Extraction

Subclass `InstagramScraper` and override parsing methods:
- `_parse_post_node()`: Customize post data extraction
- `_extract_media_urls()`: Add new media URL patterns
- `_get_media_type()`: Support additional media types

## Performance

- **Profile Scrape**: ~3-5 seconds
- **50 Posts Scrape**: ~2-3 minutes (with respectful rate limiting)
- **Memory Usage**: ~20-30 MB per session

## Future Enhancements

- [ ] MongoDB storage backend
- [ ] Proxy pool rotation
- [ ] Distributed scraping with Redis
- [ ] Video download support
- [ ] Comments and likes scraping
- [ ] Story/Reel scraping

## License

MIT License - See LICENSE file for details

## Disclaimer

This tool is for educational and research purposes only. Users are responsible for complying with Instagram's Terms of Service and local laws. Unauthorized scraping may violate Instagram's ToS. Use responsibly.

---

**Author**: Engineering Team  
**Version**: 1.0.0  
**Last Updated**: 2025-01-08
