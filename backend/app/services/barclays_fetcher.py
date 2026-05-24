"""
Automated fetcher for Barclays Smart Investor with stealth and session reuse.
Handles the complex character-selection login challenge and bot detection.
"""
from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PwTimeout

logger = logging.getLogger(__name__)


class BarclaysFetcher:
    def __init__(
        self,
        username: str,
        password: str,
        account_number: Optional[str] = None,
        headless: bool = False,  # Set to True for production, False for debugging
        use_stealth: bool = True,
        profile_path: Optional[str] = None,
    ):
        self.username = username
        self.password = password
        self.account_number = account_number
        self.headless = headless
        self.use_stealth = use_stealth
        self.profile_path = profile_path
        self.download_dir = Path(tempfile.mkdtemp(prefix="barclays_fetch_"))

    def fetch_report(self, report_type: str = "holdings") -> Optional[Path]:
        """
        Log in to Barclays Smart Investor and download a report.
        
        Args:
            report_type: 'holdings', 'statements', or 'transactions'
            
        Returns:
            Path to the downloaded file, or None on failure.
        """
        with sync_playwright() as p:
            # Launch with stealth features
            if self.use_stealth:
                browser = self._launch_stealth(p)
            else:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
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
            
            # Load existing cookies if profile path is provided
            if self.profile_path and os.path.exists(self.profile_path):
                logger.info(f"Loading cookies from profile: {self.profile_path}")
                # Playwright doesn't directly load Chrome cookies, but we can use the profile
                context = browser.new_context(
                    storage_state=f"{self.profile_path}/Default/Network/Cookies",
                )
            
            page = context.new_page()
            page.set_default_timeout(30000)
            
            download_path = None
            with page.expect_download(timeout=60000) as download_info:
                try:
                    self._login(page)
                    self._navigate_to_report(page, report_type)
                    self._click_download(page)
                    
                    download = download_info.value
                    download_path = self.download_dir / download.suggested_filename
                    download.save_as(download_path)
                    logger.info(f"Report downloaded to: {download_path}")
                    
                except Exception as e:
                    logger.error(f"Failed to download report: {e}")
                    page.screenshot(path=self.download_dir / "debug_screenshot.png")
                    raise
                    
            browser.close()
            return download_path

    def _launch_stealth(self, playwright):
        """Launch browser with stealth features to avoid detection."""
        browser = playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-gpu',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-software-rasterizer',
            ],
        )
        return browser

    def _login(self, page: Page):
        """Handle the Barclays Smart Investor login flow."""
        logger.info("Navigating to Barclays Smart Investor...")
        page.goto("https://www.smartinvestor.barclays.co.uk/", wait_until="domcontentloaded")
        
        # Wait for the login form
        try:
            username_input = page.wait_for_selector("input[name='userid'], input[placeholder*='username'], input[name='username']", timeout=15000)
            username_input.fill(self.username)
            
            password_input = page.wait_for_selector("input[type='password']", timeout=10000)
            password_input.fill(self.password)
            
            login_btn = page.wait_for_selector("button[type='submit'], input[type='submit']", timeout=10000)
            login_btn.click()
            
        except PwTimeout as e:
            logger.error(f"Failed to find login fields: {e}")
            page.screenshot(path=self.download_dir / "login_debug.png")
            raise

        # Handle the character selection challenge
        self._handle_character_challenge(page)

    def _handle_character_challenge(self, page: Page):
        """Handle the Barclays character selection challenge."""
        logger.info("Waiting for character challenge...")
        
        try:
            prompt_locator = page.wait_for_selector("text=Enter characters", timeout=30000)
            prompt_text = prompt_locator.inner_text()
            logger.info(f"Challenge prompt: {prompt_text}")
            
            positions = re.findall(r'(\d+)', prompt_text)
            positions = [int(p) for p in positions if p.isdigit()]
            logger.info(f"Positions to fill: {positions}")
            
            challenge_inputs = page.query_selector_all("input[type='text']")
            
            if len(challenge_inputs) < len(positions):
                challenge_inputs = page.query_selector_all(".challenge input, [class*='challenge'] input, .char-input")
                
            if len(challenge_inputs) < len(positions):
                challenge_inputs = page.query_selector_all("input[type='text']")
                
            if len(challenge_inputs) < len(positions):
                logger.error(f"Not enough input fields found. Expected {len(positions)}, found {len(challenge_inputs)}")
                page.screenshot(path=self.download_dir / "challenge_debug.png")
                raise Exception("Not enough input fields for character challenge")
            
            for i, pos in enumerate(positions):
                char_index = pos - 1
                if char_index < len(self.password):
                    char = self.password[char_index]
                    logger.info(f"Filling position {pos} with character '{char}'")
                    challenge_inputs[i].fill(char)
                else:
                    logger.error(f"Password too short for position {pos}")
                    
            submit_btn = page.wait_for_selector("button[type='submit'], input[type='submit']", timeout=10000)
            submit_btn.click()
            
            page.wait_for_url("**/smartinvestor/**", timeout=30000)
            
        except PwTimeout as e:
            logger.error(f"Character challenge timeout: {e}")
            page.screenshot(path=self.download_dir / "challenge_timeout.png")
            raise

    def _navigate_to_report(self, page: Page, report_type: str):
        """Navigate to the specific report section."""
        logger.info(f"Navigating to {report_type} report...")
        
        try:
            page.wait_for_selector("text=Welcome, text=Dashboard, text=Portfolio", timeout=30000)
        except PwTimeout:
            logger.warning("Dashboard element not found, proceeding anyway")
            
        report_links = {
            "holdings": "Holdings",
            "statements": "Statements",
            "transactions": "Transactions",
        }
        
        target_text = report_links.get(report_type, report_type)
        try:
            link = page.wait_for_selector(f"text={target_text}", timeout=10000)
            link.click()
            page.wait_for_load_state("networkidle", timeout=30000)
        except PwTimeout:
            logger.error(f"Could not find '{target_text}' link")
            page.screenshot(path=self.download_dir / f"report_nav_debug.png")

    def _click_download(self, page: Page):
        """Click the download button for the report."""
        logger.info("Looking for download button...")
        
        download_selectors = [
            "text=Download",
            "text=Download PDF",
            "text=Download CSV",
            "text=Download Statement",
            "a[href*='download']",
            "button[type='submit']",
        ]
        
        for selector in download_selectors:
            try:
                btn = page.wait_for_selector(selector, timeout=5000)
                btn.click()
                logger.info(f"Download triggered via selector: {selector}")
                return
            except PwTimeout:
                continue
                
        logger.error("Could not find download button")
        page.screenshot(path=self.download_dir / "download_debug.png")


if __name__ == "__main__":
    import tempfile
    
    username = os.getenv("BARCLAYS_USERNAME")
    password = os.getenv("BARCLAYS_PASSWORD")
    account_number = os.getenv("BARCLAYS_ACCOUNT_NUMBER")
    
    if not username or not password:
        print("Please set BARCLAYS_USERNAME and BARCLAYS_PASSWORD environment variables.")
        exit(1)
        
    fetcher = BarclaysFetcher(
        username=username,
        password=password,
        account_number=account_number,
        headless=False,  # Set to False to watch it run
        use_stealth=True,
    )
    
    result = fetcher.fetch_report("holdings")
    if result:
        print(f"Success! Report saved to: {result}")
    else:
        print("Failed to fetch report.")
