#!/usr/bin/env python3
import requests
import json
import time
import random
import argparse
import sys
import re
from typing import Optional, Tuple


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
                self.session.cookies.set(k, v)
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
