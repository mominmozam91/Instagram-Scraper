#!/usr/bin/env python3
import requests
import json
import time
import random
import argparse
import sys
import re
import os
from typing import Optional, Tuple
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class InstagramScraper:
    def __init__(
        self,
        username: str,
        max_posts: int = 50,
        sessionid: Optional[str] = None,
        cookie_string: Optional[str] = None,
        delay: Tuple[float, float] = (2.0, 5.0),
        ig_www_claim: Optional[str] = None,
        ig_u_ds_user_id: Optional[str] = None,
    ):
        self.username = username
        self.max_posts = int(max_posts)
        self.session = requests.Session()
        self.csrf_token: Optional[str] = None
        self.ig_www_claim = ig_www_claim
        self.ig_u_ds_user_id = ig_u_ds_user_id

        # KEY COMPONENT: Masquerade as the Instagram Web Client
        # The 'X-IG-App-ID' is critical. 936619743392459 is the public web ID.
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '129477',
            'Origin': 'https://www.instagram.com',
            'Referer': f'https://www.instagram.com/{username}/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        # Add optional custom headers if provided
        if ig_www_claim:
            self.headers['X-IG-WWW-Claim'] = ig_www_claim
        if ig_u_ds_user_id:
            self.headers['IG-U-DS-USER-ID'] = ig_u_ds_user_id

        # If running from a datacenter IP, you WILL need to add a valid 'sessionid'
        # cookie here from a browser, or use residential proxies.
        self.cookies = {}
        if sessionid:
            self.cookies['sessionid'] = sessionid
            try:
                # Ensure sessionid is sent on the very first bootstrap request
                self.session.cookies.set('sessionid', sessionid, domain='.instagram.com', path='/')
            except Exception:
                pass

        # Optional: load a full cookie string (e.g., copied from browser DevTools)
        # NOTE: This may override sessionid if also provided separately
        if cookie_string:
            self._apply_cookie_string(cookie_string)

        # Crawl-delay bounds (min, max)
        self.delay_min = max(0.0, float(delay[0]))
        self.delay_max = max(self.delay_min, float(delay[1]))

        # Prime cookies (csrftoken, mid) to reduce login-wall responses
        self.bootstrap_session()

    def bootstrap_session(self):
        """Load IG homepage to obtain cookies and CSRF token."""
        try:
            resp = self.session.get(
                'https://www.instagram.com/',
                headers={
                    'User-Agent': self.headers['User-Agent'],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': self.headers['Accept-Language'],
                },
                timeout=20,
            )
            for k, v in resp.cookies.items():
                self.session.cookies.set(k, v)
            # Merge provided cookies like sessionid
            for k, v in self.cookies.items():
                try:
                    self.session.cookies.set(k, v, domain='.instagram.com', path='/')
                except:
                    # If duplicate exists, clear and set
                    self.session.cookies.clear(domain='.instagram.com', path='/', name=k)
                    self.session.cookies.set(k, v, domain='.instagram.com', path='/')
            self.csrf_token = self._pick_csrf_token()
            if self.csrf_token:
                self.headers['X-CSRFToken'] = self.csrf_token
        except requests.RequestException:
            pass

    def _pick_csrf_token(self) -> Optional[str]:
        """Select a single csrftoken from cookie jar avoiding conflicts."""
        try:
            candidates = [c for c in self.session.cookies if c.name == 'csrftoken']
        except Exception:
            return None
        if not candidates:
            return None
        # Prefer instagram.com domain and root path
        preferred = [c for c in candidates if (c.domain.endswith('instagram.com') and c.path == '/')]
        chosen = preferred[0] if preferred else candidates[0]
        return chosen.value

    def _retry_graphql(self, url, params, max_retries=3):
        """Retry GraphQL request with exponential backoff."""
        for attempt in range(max_retries):
            try:
                headers = dict(self.headers)
                if self.csrf_token and 'X-CSRFToken' not in headers:
                    headers['X-CSRFToken'] = self.csrf_token
                
                # DEBUG: Print cookies being sent
                cookie_names = [c.name for c in self.session.cookies]
                if 'sessionid' in cookie_names:
                    try:
                        sessionid_val = self.session.cookies.get('sessionid')
                        print(f"[DEBUG] Sending sessionid: {sessionid_val[:20]}..." if sessionid_val else "[DEBUG] sessionid is empty!")
                    except:
                        print("[DEBUG] Multiple sessionid cookies found - will use them anyway")
                else:
                    print(f"[DEBUG] WARNING: sessionid NOT in cookies! Available: {cookie_names}")
                
                response = self.session.get(url, headers=headers, params=params, timeout=20)
                
                print(f"[DEBUG] GraphQL response status: {response.status_code}")
                
                if response.status_code == 200:
                    ctype = response.headers.get('Content-Type', '')
                    if 'application/json' in ctype:
                        data = response.json()
                        if 'errors' in data:
                            print(f"[DEBUG] GraphQL errors: {data.get('errors')}")
                        return data
                    else:
                        print(f"[DEBUG] GraphQL returned non-JSON content-type: {ctype}")
                        print(f"[DEBUG] Response preview: {response.text[:200]}")
                elif response.status_code in (429, 403, 503):
                    # Rate limited or forbidden; retry with backoff
                    print(f"[DEBUG] Status {response.status_code}, response: {response.text[:200]}")
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt  # 1, 2, 4 seconds
                        print(f"[*] Rate limited (status {response.status_code}), retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                else:
                    print(f"[DEBUG] Unexpected status {response.status_code}: {response.text[:200]}")
                
                return None
            except Exception as e:
                print(f"[DEBUG] Exception in GraphQL: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
        return None

    def fetch_posts_from_html(self, username: str):
        """Fallback: extract posts from profile page HTML when GraphQL fails."""
        url = f"https://www.instagram.com/{username}/"
        try:
            headers = dict(self.headers)
            headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            response = self.session.get(url, headers=headers, timeout=20)
            
            if response.status_code != 200:
                return []
            
            html = response.text
            
            # Look for shared data in script tags
            match = re.search(r'window\._sharedData\s*=\s*({.*?});', html, re.DOTALL)
            if not match:
                # Try alternate pattern
                match = re.search(r'"edge_owner_to_timeline_media":\s*{([^}]*"edges":[^\]]*\][^}]*)}}', html, re.DOTALL)
                if not match:
                    return []
            
            try:
                if match.group(0).startswith('window'):
                    # Parse the shared data object
                    data_str = match.group(1)
                    shared_data = json.loads(data_str)
                    
                    # Navigate through the structure
                    user = shared_data.get('entry_data', {}).get('ProfilePage', [{}])[0].get('graphql', {}).get('user', {})
                    timeline = user.get('edge_owner_to_timeline_media', {})
                    edges = timeline.get('edges', [])
                else:
                    # Parse individual edges
                    edges_match = re.search(r'"edges":\s*(\[.*?\])(?:,"page_info")', html, re.DOTALL)
                    if not edges_match:
                        return []
                    edges = json.loads(edges_match.group(1))
                
                posts = []
                for edge in edges[:self.max_posts]:
                    if 'node' in edge:
                        try:
                            posts.append(self.parse_post(edge['node']))
                        except:
                            continue
                return posts
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                return []
        except Exception as e:
            return []

    def _apply_cookie_string(self, cookie_str: str) -> None:
        """Parse and add semicolon-separated cookie string into the session jar."""
        try:
            parts = [p.strip() for p in cookie_str.split(';') if p.strip()]
            for part in parts:
                if '=' not in part:
                    continue
                name, value = part.split('=', 1)
                name = name.strip()
                value = value.strip()
                self.session.cookies.set(name, value, domain='.instagram.com', path='/')
                self.cookies[name] = value
        except Exception:
            pass

    def fetch_profile_initial(self):
        """
        Fetches profile metadata and the first batch of posts using the 
        internal web_profile_info endpoint.
        """
        print(f"[*] Fetching profile data for: {self.username}")
        url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={self.username}"
        
        try:
            # Use session cookies (merged) and include CSRF when available
            headers = dict(self.headers)
            if self.csrf_token and 'X-CSRFToken' not in headers:
                headers['X-CSRFToken'] = self.csrf_token
            response = self.session.get(url, headers=headers, cookies=self.session.cookies, allow_redirects=True, timeout=20)

            # Check for soft-block / login-wall
            if response.status_code in (301, 302) or "login" in response.url:
                print("[-] Error: Redirected to login. Your IP is likely flagged.")
                print("    Fix: Add a 'sessionid' cookie to the script or use a residential proxy.")
                sys.exit(1)

            response.raise_for_status()
            data = response.json()
            user = data.get('data', {}).get('user')
            if not user:
                print("[-] Error: No user data returned. The account may be private or blocked.")
                sys.exit(1)
            
            # DEBUG: Check timeline structure
            timeline = user.get('edge_owner_to_timeline_media', {})
            edges_count = len(timeline.get('edges', []))
            print(f"[DEBUG] Initial posts in response: {edges_count}")
            if edges_count == 0:
                print(f"[DEBUG] Timeline data structure: {list(timeline.keys())}")
                print(f"[DEBUG] Timeline page_info: {timeline.get('page_info', {})}")
                print(f"[DEBUG] Timeline count: {timeline.get('count', 'N/A')}")
            
            return user

        except requests.exceptions.HTTPError as e:
            print(f"[-] HTTP Error: {e}")
            sys.exit(1)
        except json.JSONDecodeError:
            print("[-] Error: Failed to parse JSON. Instagram likely returned HTML (Login wall).")
            sys.exit(1)

    def extract_profile_meta(self, user_data):
        """Extracts the required profile fields."""
        return {
            "username": user_data.get("username"),
            "full_name": user_data.get("full_name"),
            "biography": user_data.get("biography"),
            "follower_count": user_data.get("edge_followed_by", {}).get("count"),
            "following_count": user_data.get("edge_follow", {}).get("count"),
            "posts_count": user_data.get("edge_owner_to_timeline_media", {}).get("count"),
            "profile_pic_url": user_data.get("profile_pic_url_hd"),
            "is_verified": user_data.get("is_verified"),
            "category": user_data.get("category_name"),
            "external_url": user_data.get("external_url"),
        }

    def parse_post(self, node):
        """Parses a single post node from the Graph structure."""
        # Extract view count (available for videos, 0 for images)
        view_count = node.get("video_view_count") or 0
        
        return {
            "id": node.get("id"),
            "shortcode": node.get("shortcode"),
            "caption": node['edge_media_to_caption']['edges'][0]['node']['text'] if node.get("edge_media_to_caption", {}).get("edges") else "",
            "like_count": node.get("edge_media_preview_like", {}).get("count"),
            "comment_count": node.get("edge_media_to_comment", {}).get("count"),
            "view_count": view_count,
            "timestamp": node.get("taken_at_timestamp"),
            "media_type": "video" if node.get("is_video") else "image",
            "media_url": node.get("video_url") if node.get("is_video") else node.get("display_url"),
            "location": node.get("location", {}).get("name") if node.get("location") else None,
            "permalink": f"https://www.instagram.com/p/{node.get('shortcode')}/"
        }

    def fetch_graphql_next_page(self, user_id, end_cursor):
        """
        Uses the GraphQL endpoint to fetch the next page of posts.
        """
        # This query_hash is for 'User Posts'. These rotate occasionally.
        # In a full production system, we would scrape this hash dynamically from Consumer.js
        QUERY_HASH = "69cba40317214236af40e7efa697781d" 
        
        params = {
            "query_hash": QUERY_HASH,
            "variables": json.dumps({
                "id": user_id,
                "first": 15,
                "after": end_cursor
            })
        }
        
        url = "https://www.instagram.com/graphql/query/"
        data = self._retry_graphql(url, params, max_retries=3)
        
        if not data:
            print("[-] GraphQL returned non-JSON or rate-limited (likely login wall). Stopping pagination.")
            return None

        # Check for GraphQL errors (rate limiting, auth required, etc.)
        if 'errors' in data:
            print("[-] GraphQL returned errors. Likely rate-limited or authentication required.")
            print(f"    Error: {data.get('errors', [{}])[0].get('message', 'Unknown')}")
            return None
        
        return data

    def fetch_graphql_page(self, user_id: str, after: Optional[str] = None, first: int = 15):
        """Fetch a page of posts via GraphQL, allowing the first page (no cursor)."""
        QUERY_HASH = "69cba40317214236af40e7efa697781d"
        variables = {"id": user_id, "first": first}
        if after:
            variables["after"] = after
        params = {"query_hash": QUERY_HASH, "variables": json.dumps(variables)}
        url = "https://www.instagram.com/graphql/query/"
        
        data = self._retry_graphql(url, params, max_retries=3)
        if not data:
            print("[-] GraphQL request failed or returned non-JSON.")
            return None
        
        if 'errors' in data:
            print("[-] GraphQL returned errors.")
            return None
        
        return data

    def run(self, output_path: Optional[str] = None):
        # 1. Get Initial Data
        user_data = self.fetch_profile_initial()
        if not user_data:
            return

        # 2. Extract Profile Info
        profile_meta = self.extract_profile_meta(user_data)
        
        # 3. Process Initial Posts
        timeline = user_data.get("edge_owner_to_timeline_media", {})
        edges = timeline.get("edges", [])
        page_info = timeline.get("page_info", {})
        
        all_posts = []
        for edge in edges:
            if len(all_posts) >= self.max_posts:
                break
            all_posts.append(self.parse_post(edge['node']))
            
        print(f"[+] Scraped {len(all_posts)} posts (Initial Load)")
        if len(all_posts) == 0:
            print("[!] Initial timeline empty or hidden.")

        # 4. Handle Pagination
        user_id = user_data['id']
        has_next = page_info.get("has_next_page")
        end_cursor = page_info.get("end_cursor")

        # If initial response is empty, try GraphQL from scratch
        if len(all_posts) == 0 and len(all_posts) < self.max_posts:
            print("[*] Initial API returned no posts. Trying GraphQL directly...")
            data = self.fetch_graphql_page(user_id, after=None, first=15)
            if data:
                timeline = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {})
                edges = timeline.get("edges", [])
                page_info = timeline.get("page_info", {})
                for edge in edges:
                    if len(all_posts) >= self.max_posts:
                        break
                    all_posts.append(self.parse_post(edge['node']))
                has_next = page_info.get("has_next_page")
                end_cursor = page_info.get("end_cursor")
                print(f"[+] Total posts collected after GraphQL first page: {len(all_posts)}")
            else:
                print("[-] GraphQL first page also failed. Cannot proceed.")
        
        # If initial load didn't have pagination info but we have posts, ensure we continue
        if len(all_posts) > 0 and has_next is None and page_info:
            has_next = page_info.get("has_next_page")
            end_cursor = page_info.get("end_cursor")

        pagination_attempts = 0
        while len(all_posts) < self.max_posts and has_next and end_cursor and pagination_attempts < 5:
            pagination_attempts += 1
            # Random sleep to avoid bot detection
            sleep_time = random.uniform(self.delay_min, self.delay_max)
            print(f"[*] Sleeping {sleep_time:.2f}s...")
            time.sleep(sleep_time)

            cursor_preview = (end_cursor[:10] + '...') if isinstance(end_cursor, str) else 'N/A'
            print(f"[*] Fetching next page (Attempt {pagination_attempts}, Cursor: {cursor_preview})")
            data = self.fetch_graphql_next_page(user_id, end_cursor)
            
            if not data:
                print(f"[!] GraphQL pagination blocked after {pagination_attempts} attempt(s).")
                print("[*] Note: Instagram blocks GraphQL from datacenter IPs. Use a residential proxy or session from same IP.")
                break
                
            timeline = data.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {})
            edges = timeline.get("edges", [])
            page_info = timeline.get("page_info", {})
            
            for edge in edges:
                if len(all_posts) >= self.max_posts:
                    break
                all_posts.append(self.parse_post(edge['node']))
            
            has_next = page_info.get("has_next_page")
            end_cursor = page_info.get("end_cursor")
            print(f"[+] Total posts collected: {len(all_posts)}")

        # 5. Output Result
        output = {
            "profile": profile_meta,
            "posts": all_posts
        }
        
        filename = output_path or f"{self.username}_data.json"
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
            
        print(f"[SUCCESS] Data saved to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram scraper (public web)")
    parser.add_argument("username", help="Instagram username to scrape")
    parser.add_argument("-n", "--max-posts", type=int, default=50, help="Maximum number of posts to scrape (default: 50)")
    parser.add_argument("--delay-min", type=float, default=2.0, help="Minimum delay between requests (seconds)")
    parser.add_argument("--delay-max", type=float, default=5.0, help="Maximum delay between requests (seconds)")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output JSON path (default: <username>_data.json)")

    args = parser.parse_args()

    # Load credentials from environment variables
    sessionid = os.getenv('INSTAGRAM_SESSION_ID')
    cookie_string = os.getenv('INSTAGRAM_COOKIE_STRING')
    ig_www_claim = os.getenv('INSTAGRAM_WWW_CLAIM')
    ig_u_ds_user_id = os.getenv('INSTAGRAM_U_DS_USER_ID')

    if args.delay_max < args.delay_min:
        print("[-] --delay-max cannot be less than --delay-min")
        sys.exit(1)

    scraper = InstagramScraper(
        username=args.username,
        max_posts=args.max_posts,
        sessionid=sessionid,
        cookie_string=cookie_string,
        delay=(args.delay_min, args.delay_max),
        ig_www_claim=ig_www_claim,
        ig_u_ds_user_id=ig_u_ds_user_id,
    )
    scraper.run(output_path=args.output)
