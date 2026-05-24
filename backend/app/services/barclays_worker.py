"""
Background worker for fetching Barclays Smart Investor data.
Uses cookie-based authentication to bypass the login challenge.
"""
from __future__ import annotations

import os
import re
import time
import logging
import threading
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright, Page, TimeoutError as PwTimeout

logger = logging.getLogger(__name__)


@dataclass
class FetchStatus:
    status: str = "pending"  # pending, running, success, failed
    message: str = ""
    report_path: Optional[str] = None
    error: Optional[str] = None


class BarclaysWorker:
    def __init__(self):
        self.status: FetchStatus = FetchStatus()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start_fetch(self, report_type: str = "holdings") -> str:
        """Start the fetch in a background thread and return a job ID."""
        self.status = FetchStatus(status="running", message="Starting fetch...")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_fetch,
            args=(report_type,),
            daemon=True,
        )
        self._thread.start()
        return "barclays_fetch_job"  # Simple job ID for now

    def stop_fetch(self):
        """Stop the current fetch."""
        self._stop_event.set()

    def _run_fetch(self, report_type: str):
        """Run the actual Playwright automation."""
        self.status = FetchStatus(status="running", message="Logging in...")
        
        # Try cookie-based auth first, fall back to username/password
        cookie_file = os.getenv("BARCLAYS_COOKIE_FILE")
        username = os.getenv("BARCLAYS_USERNAME")
        password = os.getenv("BARCLAYS_PASSWORD")
        
        download_dir = Path(tempfile.mkdtemp(prefix="barclays_fetch_"))
        
        with sync_playwright() as p:
            # Launch with stealth features
            browser = p.chromium.launch(
                headless=False,  # Set to True for production if you have a display
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-gpu',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-GB",
                timezone_id="Europe/London",
            )
            
            # Load cookies if available
            if cookie_file and os.path.exists(cookie_file):
                try:
                    with open(cookie_file) as f:
                        import json
                        cookies = json.load(f)
                        context.add_cookies(cookies)
                    self.status = FetchStatus(status="running", message="Using saved session...")
                except Exception as e:
                    logger.warning(f"Failed to load cookies: {e}")
            
            page = context.new_page()
            page.set_default_timeout(30000)
            
            try:
                # Navigate to Smart Investor
                self.status = FetchStatus(status="running", message="Navigating to Barclays...")
                page.goto("https://www.smartinvestor.barclays.co.uk/", wait_until="domcontentloaded")
                
                # Check if already logged in
                try:
                    page.wait_for_selector("text=Portfolio", timeout=5000)
                    self.status = FetchStatus(status="running", message="Already logged in...")
                except PwTimeout:
                    # Not logged in, try cookie-based login
                    if cookie_file and os.path.exists(cookie_file):
                        # Try reloading with cookies
                        page.reload()
                        try:
                            page.wait_for_selector("text=Portfolio", timeout=10000)
                            self.status = FetchStatus(status="running", message="Logged in with cookies...")
                        except PwTimeout:
                            # Fall back to username/password
                            if username and password:
                                self._manual_login(page, username, password)
                            else:
                                self.status = FetchStatus(
                                    status="failed",
                                    message="Not logged in and no credentials configured.",
                                )
                                return
                    elif username and password:
                        self._manual_login(page, username, password)
                    else:
                        self.status = FetchStatus(
                            status="failed",
                            message="Not logged in and no credentials or cookies configured.",
                        )
                        return
                
                # Navigate to report
                self.status = FetchStatus(status="running", message="Downloading report...")
                page.click(f"text={report_type.capitalize()}")
                
                # Download
                with page.expect_download(timeout=60000) as download_info:
                    page.click("text=Download")
                
                download = download_info.value
                download_path = download_dir / download.suggested_filename
                download.save_as(download_path)
                
                self.status = FetchStatus(
                    status="success",
                    message="Report downloaded successfully.",
                    report_path=str(download_path),
                )
                
            except Exception as e:
                logger.error(f"Fetch failed: {e}")
                page.screenshot(path=download_dir / "debug.png")
                self.status = FetchStatus(
                    status="failed",
                    message=f"Failed: {str(e)}",
                    error=str(e),
                )
            finally:
                browser.close()

    def _manual_login(self, page: Page, username: str, password: str):
        """Handle manual login with username/password."""
        # Click login
        page.click("text=Log in to Online Banking")
        
        # Fill membership details
        page.fill("input[name='userid']", username)
        page.fill("input[name='membership-number']", password)
        page.click("button:has-text('Continue')")
        
        # Wait for challenge
        page.wait_for_selector("text=Enter characters", timeout=30000)
        
        # Handle character challenge
        prompt = page.text_content("text=Enter characters")
        positions = re.findall(r'(\d+)', prompt)
        positions = [int(p) for p in positions if p.isdigit()]
        
        inputs = page.query_selector_all("input[type='text']")
        for i, pos in enumerate(positions):
            char_idx = pos - 1
            if char_idx < len(password):
                inputs[i].fill(password[char_idx])
        
        page.click("button:has-text('Log in')")
        
        # Wait for dashboard
        page.wait_for_selector("text=Portfolio", timeout=30000)


# Global worker instance
worker = BarclaysWorker()
