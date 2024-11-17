import asyncio
import os
import json
from typing import List, Set, Dict, Optional
from playwright.async_api import async_playwright, Browser, Page
from urllib.parse import urljoin, urlparse
import logging
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GPTCrawler:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.visited_urls: Set[str] = set()
        self.results: List[Dict] = []
        self.running = True

    async def init_browser(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)

    async def close_browser(self):
        if self.browser:
            await self.browser.close()

    def matches_pattern(self, url: str, pattern: str) -> bool:
        if not pattern:
            return True
        return url.startswith(pattern)

    async def process_page(self, page: Page, selector: str, remove_selectors: List[str]) -> str:
        try:
            # Get the HTML content
            if selector:
                elements = await page.query_selector_all(selector)
                contents = []
                for element in elements:
                    text = await element.evaluate('el => el.textContent')
                    if text:
                        contents.append(text.strip())
                content = '\n\n'.join(contents)
            else:
                content = await page.evaluate('() => document.body.textContent')

            # Clean up the content
            content = ' '.join(content.split())
            return content

        except Exception as e:
            logger.error(f"Error processing page: {str(e)}")
            return f"Error processing page: {str(e)}"

    async def crawl_page(self, url: str, selector: str, remove_selectors: List[str]) -> List[str]:
        if not self.browser:
            await self.init_browser()

        try:
            page = await self.browser.new_page()
            await page.goto(url, wait_until='networkidle')
            
            # Get page title
            title = await page.title()
            
            # Extract content
            content = await self.process_page(page, selector, remove_selectors)
            
            # Save results
            self.results.append({
                "url": url,
                "title": title,
                "content": content
            })

            # Find all links
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(href => href.startsWith('http'));
            }''')

            # Filter links from same domain
            base_domain = urlparse(url).netloc
            filtered_links = [
                link for link in links 
                if urlparse(link).netloc == base_domain
            ]

            await page.close()
            return filtered_links

        except Exception as e:
            logger.error(f"Error crawling {url}: {str(e)}")
            return []

    async def crawl(self, 
                   start_url: str, 
                   url_pattern: str = "",
                   selector: str = "",
                   remove_selectors: List[str] = None,
                   max_pages: int = 10,
                   output_file: str = "crawler_output.json") -> None:
        """
        Main crawling function
        """
        self.running = True
        self.visited_urls.clear()
        self.results.clear()
        remove_selectors = remove_selectors or []
        
        try:
            # First get the page title
            if not self.browser:
                await self.init_browser()
            page = await self.browser.new_page()
            await page.goto(start_url, wait_until='networkidle')
            page_title = await page.title()
            await page.close()
            
            # Clean the title for use in filename
            clean_title = "".join(c for c in page_title if c.isalnum() or c in (' ', '-', '_')).strip()
            clean_title = clean_title.replace(' ', '_')[:50]  # Limit length and replace spaces
            
            # Generate unique filename with timestamp and title
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, ext = os.path.splitext(output_file)
            unique_output_file = f"{filename}_{clean_title}_{timestamp}{ext}"
            
            urls_to_visit = {start_url}
            
            while urls_to_visit and len(self.visited_urls) < max_pages and self.running:
                url = urls_to_visit.pop()
                
                if url in self.visited_urls:
                    continue
                    
                if not self.matches_pattern(url, url_pattern):
                    continue

                logger.info(f"Crawling: {url}")
                self.visited_urls.add(url)
                
                new_urls = await self.crawl_page(url, selector, remove_selectors)
                urls_to_visit.update(set(new_urls) - self.visited_urls)

            # Get domain name for metadata
            domain = urlparse(start_url).netloc

            # Ensure output directory exists
            os.makedirs(os.path.dirname(os.path.abspath(unique_output_file)), exist_ok=True)

            # Save results with additional metadata
            with open(unique_output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "metadata": {
                        "title": page_title,
                        "domain": domain,
                        "crawl_date": datetime.now().isoformat(),
                        "total_pages": len(self.results),
                        "start_url": start_url,
                        "pattern": url_pattern
                    },
                    "pages": self.results
                }, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Crawling completed. Processed {len(self.visited_urls)} pages.")
            logger.info(f"Results saved to: {unique_output_file}")
            
        except Exception as e:
            logger.error(f"Crawling error: {str(e)}")
        finally:
            self.running = False
            await self.close_browser()

    def stop(self):
        """Stop the crawling process"""
        self.running = False 