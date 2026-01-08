# Instagram Raw Data Acquisition System Architecture

## 1. System Overview

The scraper system is designed as a scalable, production-grade architecture for continuously collecting raw Instagram profile and post data from public accounts. It uses pure HTTP requests with HTML/JSON parsing, avoiding browser automation to maintain efficiency and reduce resource consumption.

## 2. How Data Access Works

### A. Instagram Public Data Endpoints

**Primary Data Sources:**
- **Initial Profile Load**: HTML page contains embedded JSON in `<script>` tags with key profile metadata
- **GraphQL Endpoint** (`/graphql/query`): Returns paginated post data in JSON format
- **API Structure**: Instagram embeds `window._sharedData` JavaScript object containing initial profile and post data
- **GraphQL Variables**: Post pagination uses queryId `17888483320059182` with cursor-based pagination

**Data Flow:**
1. Request Instagram profile page (`https://www.instagram.com/{username}/`)
2. Extract embedded JSON from HTML script tags
3. Parse profile metadata from JSON
4. Use GraphQL endpoint with pagination cursors to fetch additional posts
5. Extract post data, media URLs, and engagement metrics

### B. Scraper Architecture

**Multi-Component Design:**

```
┌─────────────────────────────────────────────┐
│     Task Queue / Job Scheduler              │
│  (Redis/Celery alternative: simple queue)   │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│    Worker Pool (Async HTTP Requests)        │
│  - 3-5 concurrent workers per host          │
│  - Rate limiting: 1 request per 2 seconds   │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│      Scraper Module                         │
│  - Profile Fetcher                          │
│  - Post Fetcher with Pagination             │
│  - HTML/JSON Parser                         │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│    Data Store (PostgreSQL/MongoDB)          │
│  - Profile cache with TTL                   │
│  - Post data with deduplication             │
│  - Session/proxy management                 │
└─────────────────────────────────────────────┘
```

**Key Components:**

1. **Username Discovery & Queueing**
   - Manual seed list of target accounts
   - Related account discovery via profile bio links and hashtags
   - Queue management with priority levels (hot accounts vs. cold)
   - Deduplication to prevent re-scraping same accounts within TTL

2. **Worker Management**
   - Concurrent workers (limited to 3-5 per host to avoid rate limits)
   - Each worker handles retries independently
   - Session persistence for IP reputation
   - Automatic rate limiting between requests

3. **Retry & Backoff Strategy**
   - **Initial Retry**: Immediate (for transient network errors)
   - **Backoff Schedule**: 
     - 1st retry: 5 seconds
     - 2nd retry: 30 seconds
     - 3rd retry: 5 minutes
     - 4th+ retry: Exponential (2^n minutes, max 24 hours)
   - **Max Retries**: 5 attempts per request
   - **Circuit Breaker**: Account marked as "banned" after 5 consecutive 429/403 responses

4. **Block Detection & Prevention**
   - **429 (Too Many Requests)**: Backoff exponentially, wait before retry
   - **403 (Forbidden)**: Account likely shadowbanned or IP blocked
   - **404 (Not Found)**: Account deleted or private (mark as inactive)
   - **Response Signature Check**: Verify JSON structure; incomplete responses indicate throttling
   - **Session Rotation**: Switch to new session/IP after 3 consecutive blocks

5. **Proxy Rotation Strategy**
   - Pool of 10-20 rotating residential proxies
   - Rotate proxy every 50 requests per IP
   - Fallback to bare IP if proxy fails (with increased backoff)
   - Geographic diversity: Mix of US/EU proxies to avoid regional blocks
   - Proxy health monitoring: Remove dead proxies from rotation

6. **User-Agent Strategy**
   - Rotate user agents from pool of 15+ modern browser signatures
   - Browser versions: Chrome, Safari, Firefox (recent releases)
   - Device types: Mix of desktop and mobile user agents
   - No obvious bot signatures (avoid "bot", "scraper", "curl")
   - User-Agent rotation: Every 20 requests or per IP change

## 3. Raw Data Collected

### Profile Data
```json
{
  "username": "string",
  "full_name": "string",
  "biography": "string",
  "follower_count": "integer",
  "following_count": "integer",
  "posts_count": "integer",
  "profile_picture_url": "string (URL)",
  "is_verified": "boolean",
  "category": "string or null",
  "external_url": "string (URL) or null",
  "is_private": "boolean",
  "is_business": "boolean",
  "timestamp_scraped": "ISO8601 datetime"
}
```

### Posts Data
```json
{
  "id": "string (unique post ID)",
  "shortcode": "string",
  "caption": "string or null",
  "like_count": "integer",
  "view_count": "integer or null",
  "comment_count": "integer",
  "timestamp": "ISO8601 datetime",
  "media_type": "enum: IMAGE, CAROUSEL, VIDEO, REEL",
  "media_urls": ["string (URL array)"],
  "location": "string or null",
  "permalink": "string (https://www.instagram.com/p/{shortcode}/)",
  "username": "string (post owner)"
}
```

## 4. Frequency & Scheduling

**Scheduling Policy:**
- **Profiles**: Re-scrape every 24 hours (followers/following changes slowly)
- **Posts**: Re-scrape every 6 hours for active accounts, 24 hours for inactive
- **High-Priority Accounts** (e.g., influencers): Scrape every 2 hours
- **Initial Crawl**: Full pagination on first scrape (all posts)
- **Refresh**: Only fetch new posts since last cursor on subsequent runs

**Scheduling Implementation:**
- APScheduler for local scheduling
- Cron-like syntax for recurring jobs
- Exponential backoff for failing accounts
- Distributed scheduling via Redis for multi-machine deployments

## 5. Error Handling & Resilience

**Monitoring & Alerting:**
- Log all requests with timestamps, IP, user agent, response code
- Alert on consecutive block patterns
- Track scraper health metrics (success rate, average response time)
- Graceful degradation: Skip failed account, continue with queue

**Data Consistency:**
- Deduplication by post ID before storing
- Timestamp-based versioning (keep historical data)
- Validate JSON schema before insertion
- Rollback on partial failures

## 6. Deployment Considerations

- **Containerization**: Docker for consistent environment
- **Scalability**: Horizontal scaling via worker processes
- **State Management**: Redis for session cache, IP reputation
- **Logging**: Centralized logging (ELK stack) for debugging
- **Rate Limiting**: Token bucket algorithm for request throttling

---

This architecture balances scalability, reliability, and respect for Instagram's Terms of Service by implementing thoughtful rate limiting and user-agent rotation rather than aggressive scraping.
