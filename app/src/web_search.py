# ---------------------------------------------------------------------
#   Web search utility using DuckDuckGo, Bing, and Google.
# -------------------------------------------------------------------
from bs4 import BeautifulSoup
import aiohttp
from urllib.parse import quote_plus, urlparse, parse_qs
import asyncio

# ---------------------------------------------------------------------
#   Handles web searching via multiple engines (DDG, Bing, Google).
# -------------------------------------------------------------------
class WebSearch:
    def __init__(self, query):
        self.query = query
        # Using a more comprehensive header to better mimic a real browser request
        # This can help bypass simple anti-bot measures.
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            # Removed 'br' (Brotli) to avoid dependency issues with aiohttp if the 'brotli' package is not installed.
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }

    # ---------------------------------------------------------------------
    #   Fetches and extracts text content from a URL.
    # -------------------------------------------------------------------
    async def _get_page_content(self, session, url: str) -> str:
        """Fetches and extracts a text snippet from a given URL."""
        if not url or not url.startswith('http'):
            return "Snippet not available (invalid URL)."
        try:
            # Use a timeout to avoid hanging on slow pages
            async with session.get(url, timeout=8) as response:
                if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                    return f"Snippet not available (status: {response.status})."
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove script and style elements to clean up the text
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()
                
                # Find main content area, falling back to the body
                main_content = soup.find('main') or soup.find('article') or soup.body
                if not main_content:
                    return "Snippet not available (no body content)."

                text = main_content.get_text(separator=' ', strip=True)
                snippet = ' '.join(text.split()[:150]) # Limit to ~150 words
                return snippet + '...' if len(text.split()) > 150 else snippet
        except Exception as e:
            return f"Snippet not available (error: {e})."

    # ---------------------------------------------------------------------
    #   Performs search on Google.
    # -------------------------------------------------------------------
    async def _search_google(self):
        """Performs a search on Google. Less reliable due to anti-scraping."""
        if not self.query or not self.query.strip():
            return []

        encoded_query = quote_plus(self.query)
        url = f"https://www.google.com/search?q={encoded_query}&hl=en"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    results = []
                    # Google's CSS classes change. This is a best-effort attempt.
                    for container in soup.find_all('div', class_='yuRUbf'):
                        link_tag = container.find('a')
                        title_tag = container.find('h3')
                        if link_tag and title_tag and link_tag.has_attr('href'):
                            results.append({'title': title_tag.text, 'link': link_tag['href']})
                    
                    if not results:
                        print(f"[Debug] Google returned no results. Saving page content to debug_google.html")
                        with open("debug_google.html", "w", encoding="utf-8") as f:
                            f.write(soup.prettify())
                    return results
        except aiohttp.ClientError as e:
            print(f"An error occurred during Google search: {e}")
            return []

    # ---------------------------------------------------------------------
    #   Performs search on DuckDuckGo.
    # -------------------------------------------------------------------
    async def _search_duckduckgo(self):
        """Performs a search on DuckDuckGo's HTML version. More reliable for scraping."""
        if not self.query or not self.query.strip():
            return []
            
        encoded_query = quote_plus(self.query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        try:
            # DDG is less strict, so we can use a simpler header from the main set
            ddg_headers = {'User-Agent': self.headers['User-Agent']}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=ddg_headers) as response:
                    response.raise_for_status()
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    results = []
                    for container in soup.find_all('div', class_='result'):
                        link_tag = container.find('a', class_='result__a')
                        if link_tag and link_tag.has_attr('href'):
                            title = link_tag.text
                            # DuckDuckGo HTML links are redirects. We need to parse the real URL.
                            redirect_url = link_tag['href']
                            parsed_url = urlparse(redirect_url)
                            query_params = parse_qs(parsed_url.query)
                            actual_url = query_params.get('uddg', [None])[0]
                            if actual_url:
                                results.append({'title': title, 'link': actual_url})
                    
                    if not results:
                        print(f"[Debug] DuckDuckGo returned no results. Saving page content to debug_duckduckgo.html")
                        with open("debug_duckduckgo.html", "w", encoding="utf-8") as f:
                            f.write(soup.prettify())
                    return results
        except aiohttp.ClientError as e:
            print(f"An error occurred during DuckDuckGo search: {e}")
            return []

    # ---------------------------------------------------------------------
    #   Performs search on Bing.
    # -------------------------------------------------------------------
    async def _search_bing(self):
        """Performs a search on Bing."""
        if not self.query or not self.query.strip():
            return []

        encoded_query = quote_plus(self.query)
        url = f"https://www.bing.com/search?q={encoded_query}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    results = []
                    for container in soup.find_all('li', class_='b_algo'):
                        link_tag = container.find('h2').find('a') if container.find('h2') else None
                        if link_tag and link_tag.has_attr('href'):
                            title = link_tag.text
                            link = link_tag['href']
                            results.append({'title': title, 'link': link})
                    
                    if not results:
                        print(f"[Debug] Bing returned no results. Saving page content to debug_bing.html")
                        with open("debug_bing.html", "w", encoding="utf-8") as f:
                            f.write(soup.prettify())
                    return results
        except aiohttp.ClientError as e:
            print(f"An error occurred during Bing search: {e}")
            return []

    # ---------------------------------------------------------------------
    #   Orchestrates the search across engines and fetches content.
    # -------------------------------------------------------------------
    async def search(self):
        """
        Searches the web, then fetches content snippets for the top results.
        Tries DuckDuckGo first, then Bing, then Google.
        """
        if not self.query or not self.query.strip():
            return []

        raw_results = []
        print("Attempting search with DuckDuckGo...")
        raw_results = await self._search_duckduckgo()
        if raw_results:
            print("Found results with DuckDuckGo.")
        
        if not raw_results:
            print("DuckDuckGo returned no results. Trying Bing...")
            raw_results = await self._search_bing()
            if raw_results:
                print("Found results with Bing.")
        
        if not raw_results:
            print("Bing returned no results. Trying Google...")
            raw_results = await self._search_google()
            if raw_results:
                print("Found results with Google.")

        if not raw_results:
            print("All search engines failed or returned no results.")
            return []

        top_results = raw_results[:5]
        print("Fetching content snippets for top results...")
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [self._get_page_content(session, result['link']) for result in top_results]
            snippets = await asyncio.gather(*tasks)

        for i, result in enumerate(top_results):
            result['snippet'] = snippets[i]
            
        return top_results
    
    # ---------------------------------------------------------------------
    #   Returns the current query string.
    # -------------------------------------------------------------------
    def get_query(self):
        return self.query
    
    # ---------------------------------------------------------------------
    #   Sets the query string.
    # -------------------------------------------------------------------
    def set_query(self, query):
        self.query = query
        return self.query
    
    # ---------------------------------------------------------------------
    #   Public accessor for search results.
    # -------------------------------------------------------------------
    async def get_results(self):
        return await self.search()