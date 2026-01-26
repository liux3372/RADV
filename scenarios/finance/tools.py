import json
import os
import re
import traceback
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, Any

import aiohttp
import backoff
import ssl
import certifi
from bs4 import BeautifulSoup

from model_library.base import LLM, ToolBody, ToolDefinition

# Create SSL context with certifi certificates
ssl_context = ssl.create_default_context(cafile=certifi.where())

MAX_END_DATE = "2025-04-07"


class RateLimiter:
    """Simple rate limiter to ensure minimum delay between API calls."""
    
    def __init__(self, min_delay_seconds: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            min_delay_seconds: Minimum delay in seconds between consecutive calls
        """
        self.min_delay_seconds = min_delay_seconds
        self._last_call_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self) -> None:
        """Wait if necessary to maintain minimum delay between calls."""
        async with self._lock:
            if self._last_call_time is not None:
                elapsed = time.time() - self._last_call_time
                if elapsed < self.min_delay_seconds:
                    wait_time = self.min_delay_seconds - elapsed
                    await asyncio.sleep(wait_time)
            self._last_call_time = time.time()


# Global rate limiter for Gemini API calls
# Can be configured via GEMINI_API_MIN_DELAY environment variable (default: 1.0 seconds)
_gemini_rate_limiter = RateLimiter(
    min_delay_seconds=float(os.getenv("GEMINI_API_MIN_DELAY", "1.0"))
)


def is_429(exception) -> bool:
    is429 = (
        isinstance(exception, aiohttp.ClientResponseError)
        and exception.status == 429
        or "429" in str(exception)
    )
    return is429


# Define a reusable backoff decorator for 429 errors. Mainly used for the SEC and Google Search APIs.
def retry_on_429(func):
    @backoff.on_exception(
        backoff.expo,
        aiohttp.ClientResponseError,
        max_tries=8,
        base=2,
        factor=3,
        jitter=backoff.full_jitter,
        giveup=lambda e: not is_429(e),
    )
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


class Tool(ABC):
    """
    Abstract base class for tools.
    """

    name: str
    description: str
    input_arguments: dict
    required_arguments: list[str]

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__()

    def get_tool_definition(self) -> ToolDefinition:
        body = ToolBody(
            name=self.name,
            description=self.description,
            properties=self.input_arguments,
            required=self.required_arguments,
        )

        definition = ToolDefinition(name=self.name, body=body)

        return definition

    @abstractmethod
    async def call_tool(self, arguments: dict, *args, **kwargs) -> Any:
        pass

    async def __call__(self, arguments: dict[str, Any] | None = None, *args, **kwargs) -> dict[str, Any]:
        try:
            if arguments is None:
                arguments = {}
            tool_result = await self.call_tool(arguments, *args, **kwargs)
            if self.name == "retrieve_information":
                return {
                    "success": True,
                    "result": tool_result["retrieval"],
                    "usage": tool_result["usage"],
                }
            else:
                return {"success": True, "result": json.dumps(tool_result)}
        except Exception as e:
            is_verbose = os.environ.get("EDGAR_AGENT_VERBOSE", "0") == "1"
            error_msg = str(e)
            if is_verbose:
                error_msg += f"\nTraceback: {traceback.format_exc()}"
            return {"success": False, "result": error_msg}


class GoogleWebSearch(Tool):
    name: str = "google_web_search"
    description: str = "Search the web for information"
    input_arguments: dict = {
        "search_query": {
            "type": "string",
            "description": "The query to search for",
        }
    }
    required_arguments: list[str] = ["search_query"]

    def __init__(
        self,
        top_n_results: int = 10,
        serpapi_api_key: str | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(
            self.name,
            self.description,
            self.input_arguments,
            self.required_arguments,
            *args,
            **kwargs,
        )
        self.top_n_results = top_n_results
        if serpapi_api_key is None:
            serpapi_api_key = os.getenv("SERP_API_KEY")
        # Strip whitespace to handle any accidental spaces in environment variable
        if serpapi_api_key:
            self.serpapi_api_key = serpapi_api_key.strip()
        else:
            self.serpapi_api_key = None

    @retry_on_429
    async def _execute_search(self, search_query: str) -> list[dict[str, Any]]:
        """
        Search the web for information using Google Search via SerpAPI.

        Args:
            search_query (str): The query to search for

        Returns:
            list[dict[str, Any]]: A list of search result dictionaries from SerpAPI (each containing title, link, snippet, etc.)
        """
        # Validate API key - check for None, empty string, or whitespace-only
        if not self.serpapi_api_key or not self.serpapi_api_key.strip():
            env_key = os.getenv("SERP_API_KEY")
            if not env_key or not env_key.strip():
                raise ValueError(
                    "SERP_API_KEY environment variable is not set or is empty. "
                    "Please set SERP_API_KEY in your environment or GitHub Actions secrets."
                )
            else:
                raise ValueError(
                    "SERP_API_KEY is not properly initialized. "
                    f"Environment variable exists but was not passed to GoogleWebSearch. "
                    f"Key length: {len(env_key)} characters."
                )

        params = {
            "api_key": self.serpapi_api_key.strip(),  # Remove any whitespace
            "engine": "google",
            "q": search_query,
            "num": self.top_n_results,
            # Hardcode date limit to April 7, 2025
            "tbs": "cdr:1,cd_max:04/07/2025",
        }

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                "https://serpapi.com/search.json", params=params
            ) as response:
                # Handle 401 Unauthorized specifically
                if response.status == 401:
                    error_text = await response.text()
                    try:
                        error_json = json.loads(error_text)
                        error_msg = error_json.get("error", error_text or "Unauthorized")
                    except:
                        error_msg = error_text if error_text else "Unauthorized"
                    
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=401,
                        message=(
                            f"SerpAPI authentication failed (401 Unauthorized). "
                            f"Error: {error_msg}\n\n"
                            f"Possible causes:\n"
                            f"1. SERP_API_KEY is missing or not set in GitHub Actions secrets\n"
                            f"2. SERP_API_KEY is invalid or expired\n"
                            f"3. API key has incorrect format (should not have quotes or extra whitespace)\n"
                            f"4. API key was not properly passed to the Docker container\n\n"
                            f"To fix:\n"
                            f"- Verify SERP_API_KEY is set in GitHub repository secrets\n"
                            f"- Check that the secret name matches exactly: SERP_API_KEY\n"
                            f"- Ensure the API key is valid at https://serpapi.com/dashboard\n"
                            f"- Check Docker container logs to verify environment variable is set"
                        )
                    )
                
                response.raise_for_status()  # This will raise ClientResponseError for other errors
                results = await response.json()

        return results.get("organic_results", [])

    async def call_tool(self, arguments: dict) -> list[dict[str, Any]]:
        results = await self._execute_search(**arguments)
        return results


class EDGARSearch(Tool):
    name: str = "edgar_search"
    description: str = (
        """
    Search the EDGAR Database through the SEC API.
    You should provide a query, a list of form types, a list of CIKs, a start date, an end date, a page number, and a top N results.
    The results are returned as a list of dictionaries, each containing the metadata for a filing. It does not contain the full text of the filing.
    """.strip()
    )
    input_arguments: dict = {
        "query": {
            "type": "string",
            "description": "The keyword or phrase to search, such as 'substantial doubt' OR 'material weakness'",
        },
        "form_types": {
            "type": "array",
            "description": "Limits search to specific SEC form types (e.g., ['8-K', '10-Q']) list of strings. Default is None (all form types)",
            "items": {"type": "string"},
        },
        "ciks": {
            "type": "array",
            "description": "Filters results to filings by specified CIKs, type list of strings. Default is None (all filers).",
            "items": {"type": "string"},
        },
        "start_date": {
            "type": "string",
            "description": "Start date for the search range in yyyy-mm-dd format. Used with endDate to define the date range. Example: '2024-01-01'. Default is 30 days ago",
        },
        "end_date": {
            "type": "string",
            "description": "End date for the search range, in the same format as startDate. Default is today",
        },
        "page": {
            "type": "string",
            "description": "Pagination for results. Default is '1'",
        },
        "top_n_results": {
            "type": "integer",
            "description": "The top N results to return after the query. Useful if you are not sure the result you are loooking for is ranked first after your query.",
        },
    }
    required_arguments: list[str] = [
        "query",
        "form_types",
        "ciks",
        "start_date",
        "end_date",
        "page",
        "top_n_results",
    ]

    def __init__(
        self,
        sec_api_key: str | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )
        if sec_api_key is None:
            sec_api_key = os.getenv("SEC_EDGAR_API_KEY")
        self.sec_api_key = sec_api_key
        self.sec_api_url = "https://api.sec-api.io/full-text-search"

    @retry_on_429
    async def _execute_search(
        self,
        query: str,
        form_types: list[str] | str,
        ciks: list[str] | str,
        start_date: str,
        end_date: str,
        page: int,
        top_n_results: int,
    ) -> list[dict[str, Any]]:
        """
        Search the EDGAR Database through the SEC API asynchronously.

        Args:
            query (str): The keyword or phrase to search
            form_types (list[str]): List of form types to search
            ciks (list[str]): List of CIKs to filter by
            start_date (str): Start date for the search range in yyyy-mm-dd format
            end_date (str): End date for the search range in yyyy-mm-dd format
            page (int): Pagination for results
            top_n_results (int): The top N results to return

        Returns:
            list[dict[str, Any]]: A list of filing result dictionaries (each containing metadata for a filing)
        """

        if not self.sec_api_key:
            raise ValueError("SEC_EDGAR_API_KEY is not set")

        # Parse form_types if it's a string representation of a JSON array
        if (
            isinstance(form_types, str)
            and form_types.startswith("[")
            and form_types.endswith("]")
        ):
            form_types_str = form_types  # Store string value for type narrowing
            try:
                form_types = json.loads(form_types_str.replace("'", '"'))
            except json.JSONDecodeError:
                # Fallback to simple parsing if JSON parsing fails
                form_types = [
                    item.strip(" \"'") for item in form_types_str[1:-1].split(",")
                ]

        # Parse ciks if it's a string representation of a JSON array
        if isinstance(ciks, str) and ciks.startswith("[") and ciks.endswith("]"):
            ciks_str = ciks  # Store string value for type narrowing
            try:
                ciks = json.loads(ciks_str.replace("'", '"'))
            except json.JSONDecodeError:
                # Fallback to simple parsing if JSON parsing fails
                ciks = [item.strip(" \"'") for item in ciks_str[1:-1].split(",")]

        if end_date > MAX_END_DATE:
            end_date = MAX_END_DATE

        payload = {
            "query": query,
            "formTypes": form_types,
            "ciks": ciks,
            "startDate": start_date,
            "endDate": end_date,  # This will always be at most "2025-04-07"
            "page": page,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.sec_api_key,
        }

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                self.sec_api_url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()  # This will raise ClientResponseError
                result = await response.json()

        return result.get("filings", [])[: int(top_n_results)]

    async def call_tool(self, arguments: dict) -> list[dict[str, Any]]:
        try:
            return await self._execute_search(**arguments)
        except Exception as e:
            is_verbose = os.environ.get("EDGAR_AGENT_VERBOSE", "0") == "1"
            if is_verbose:
                raise Exception(f"SEC API error: {e}\nTraceback: {traceback.format_exc()}")
            else:
                raise Exception(f"SEC API error: {e}")


class ParseHtmlPage(Tool):
    name: str = "parse_html_page"
    description: str = (
        """
        Parse an HTML page. This tool is used to parse the HTML content of a page and saves the content outside of the conversation to avoid context window issues.
        You should provide both the URL of the page to parse, as well as the key you want to use to save the result in the agent's data structure.
        The data structure is a dictionary.
    """.strip()
    )

    input_arguments: dict = {
        "url": {"type": "string", "description": "The URL of the HTML page to parse"},
        "key": {
            "type": "string",
            "description": "The key to use when saving the result in the conversation's data structure (dict).",
        },
    }
    required_arguments: list[str] = ["url", "key"]

    def __init__(
        self, headers: dict = {"User-Agent": "ValsAI/antoine@vals.ai"}, *args, **kwargs
    ):
        super().__init__(
            *args,
            **kwargs,
        )
        self.headers = headers

    @retry_on_429
    async def _parse_html_page(self, url: str) -> str:
        """
        Helper method to parse an HTML page and extract its text content.

        Args:
            url (str): The URL of the HTML page to parse

        Returns:
            str: The parsed text content
        """
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.get(
                    url, headers=self.headers, timeout=60
                ) as response:
                    response.raise_for_status()
                    html_content = await response.text()
            except Exception as e:
                if len(str(e)) == 0:
                    raise TimeoutError(
                        "Timeout error when parsing HTML page after 60 seconds. The URL might be blocked or the server is taking too long to respond."
                    )
                else:
                    is_verbose = os.environ.get("EDGAR_AGENT_VERBOSE", "0") == "1"
                    if is_verbose:
                        raise Exception(
                            str(e) + "\nTraceback: " + traceback.format_exc()
                        )
                    else:
                        raise Exception(str(e))

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        # Get text
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    async def _save_tool_output(
        self, output: str, key: str, data_storage: dict
    ) -> str:
        """
        Save the parsed HTML text to the data_storage dictionary.

        Args:
            output (str): The parsed text output from _parse_html_page
            key (str): The key to use when saving the result
            data_storage (dict): The dictionary to save the results to

        Returns:
            str: A status message indicating success and listing current keys
        """
        if not output:
            return ""

        tool_result = ""
        if key in data_storage:
            tool_result = "WARNING: The key already exists in the data storage. The new result overwrites the old one.\n"
        tool_result += (
            f"SUCCESS: The result has been saved to the data storage under the key: {key}."
            + "\n"
        )

        data_storage[key] = output

        keys_list = "\n".join(data_storage.keys())
        tool_result += (
            f"""
        The data_storage currently contains the following keys:
        {keys_list}
        """.strip()
            + "\n"
        )

        return tool_result

    async def call_tool(self, arguments: dict, data_storage: dict) -> str:
        """
        Parse an HTML page and return a status message.

        Args:
            arguments (dict): Dictionary containing 'url' and 'key'
            data_storage (dict): The dictionary to save the parsed content to

        Returns:
            str: A status message indicating success and listing current keys
        """
        url = arguments.get("url")
        key = arguments.get("key")
        
        if not url or not isinstance(url, str):
            raise ValueError("'url' argument is required and must be a string")
        if not key or not isinstance(key, str):
            raise ValueError("'key' argument is required and must be a string")
        
        text_output = await self._parse_html_page(url)
        tool_result = await self._save_tool_output(text_output, key, data_storage)

        return tool_result


class RetrieveInformation(Tool):
    name: str = "retrieve_information"
    description: str = (
        """
    Retrieve information from the conversation's data structure (dict) and allow character range extraction.

    IMPORTANT: Your prompt MUST include at least one key from the data storage using the exact format: {{key_name}}

    For example, if you want to analyze data stored under the key "financial_report", your prompt should look like:
    "Analyze the following financial report and extract the revenue figures: {{financial_report}}"

    The {{key_name}} will be replaced with the actual content stored under that key before being sent to the LLM.
    If you don't use this exact format with double braces, the tool will fail to retrieve the information.

    You can optionally specify character ranges for each document key to extract only portions of documents. That can be useful to avoid token limit errors or improve efficiency by selecting only part of the document.
    For example, if "financial_report" contains "Annual Report 2023" and you specify a range [1, 5] for that key,
    only "nnual" will be inserted into the prompt.

    The output is the result from the LLM that receives the prompt with the inserted data.
    
    NOTE: This tool makes a Gemini API call each time it's invoked. A single user query can trigger multiple 
    API calls (agent reasoning + tool invocations + answer synthesis), which may hit rate limits on free-tier API keys.
    """.strip()
    )
    input_arguments: dict = {
        "prompt": {
            "type": "string",
            "description": "The prompt that will be passed to the LLM. You MUST include at least one data storage key in the format {{key_name}} - for example: 'Summarize this 10-K filing: {{company_10k}}'. The content stored under each key will replace the {{key_name}} placeholder.",
        },
        "input_character_ranges": {
            "type": "array",
            "description": "An array mapping document keys to their character ranges. Each range should be an array where the first element is the start index and the second element is the end index. Can be used to only read portions of documents. By default, the full document is used. To use the full document, set the range to an empty list [].",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 0,
                        "maxItems": 2,
                    },
                },
                "required": ["key", "range"],
            },
        },
    }
    required_arguments: list[str] = ["prompt"]

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
        )

    async def call_tool(
        self, arguments: dict, data_storage: dict, model: LLM, *args, **kwargs
    ) -> dict[str, Any]:
        prompt = arguments.get("prompt")
        if not prompt or not isinstance(prompt, str):
            raise ValueError("'prompt' argument is required and must be a string")
        
        input_character_ranges = arguments.get("input_character_ranges", [])
        if input_character_ranges is None:
            input_character_ranges = []

        input_character_ranges = {
            item["key"]: item["range"] for item in input_character_ranges
        }

        # Verify that the prompt contains at least one placeholder in the correct format
        if not re.search(r"{{[^{}]+}}", prompt):
            raise ValueError(
                "ERROR: Your prompt must include at least one key from data storage in the format {{key_name}}. Please try again with the correct format."
            )

        # Find all keys in the prompt
        keys = re.findall(r"{{([^{}]+)}}", prompt)
        formatted_data = {}

        # Apply character range to each document before substitution
        for key in keys:
            if key not in data_storage:
                raise KeyError(
                    f"ERROR: The key '{key}' was not found in the data storage. Available keys are: {', '.join(data_storage.keys())}"
                )

            # Extract the specified character range from the document if provided
            doc_content = data_storage[key]

            if key in input_character_ranges:
                char_range = input_character_ranges[key]
                if len(char_range) == 0:
                    formatted_data[key] = doc_content
                elif len(char_range) != 2:
                    raise ValueError(
                        f"ERROR: The character range for key '{key}' must be an list with two elements or an empty list. Please try again with the correct format."
                    )
                else:
                    start_idx = int(char_range[0])
                    end_idx = int(char_range[1])
                    formatted_data[key] = doc_content[start_idx:end_idx]
            else:
                # Use the full document if no range is specified
                formatted_data[key] = doc_content

        # Convert {{key}} format to Python string formatting
        formatted_prompt = re.sub(r"{{([^{}]+)}}", r"{\1}", prompt)

        try:
            prompt = formatted_prompt.format(**formatted_data)
        except KeyError as e:
            raise KeyError(
                f"ERROR: The key {e} was not found in the data storage. Available keys are: {', '.join(data_storage.keys())}"
            )

        # Rate limit: Wait if needed before making API call
        await _gemini_rate_limiter.wait_if_needed()
        
        # Wrap model.query with rate limit handling and retry logic
        max_retries = 3
        retry_delay = 5.0  # Default retry delay in seconds
        
        for attempt in range(max_retries + 1):
            try:
                response = await model.query(prompt)
                break  # Success, exit retry loop
            except Exception as e:
                error_msg = str(e)
                error_msg_lower = error_msg.lower()
                
                # Check for quota/rate limit errors
                is_quota_error = any(keyword in error_msg_lower for keyword in [
                    "rate limit", "429", "quota", "resource_exhausted", 
                    "too many requests", "free_tier", "quota exceeded"
                ])
                
                if is_quota_error:
                    # Try to extract retry delay from error message
                    retry_delay_match = None
                    try:
                        # Extract retry delay from error message if present
                        if "retry in" in error_msg_lower:
                            delay_match = re.search(r'retry in ([\d.]+)s', error_msg_lower)
                            if delay_match:
                                retry_delay_match = float(delay_match.group(1))
                    except Exception:
                        pass
                    
                    retry_delay = retry_delay_match if retry_delay_match else retry_delay
                    
                    # Extract quota information if available
                    quota_info = ""
                    if "free_tier" in error_msg_lower:
                        quota_info = "\n⚠️ FREE TIER QUOTA EXCEEDED ⚠️\n"
                        # Parse specific quota violations from error message
                        violations = []
                        if "input_token_count" in error_msg_lower or "input_token_count" in error_msg:
                            violations.append("- Input tokens per minute limit exceeded")
                        if "generate_content_free_tier_requests" in error_msg:
                            # Check for per-minute vs per-day
                            if "PerMinute" in error_msg or "per minute" in error_msg_lower:
                                violations.append("- Requests per minute limit exceeded")
                            if "PerDay" in error_msg or "per day" in error_msg_lower:
                                violations.append("- Requests per day limit exceeded (daily quota exhausted)")
                        
                        if violations:
                            quota_info += "\n".join(violations) + "\n"
                        else:
                            # Fallback parsing
                            if "input_token" in error_msg_lower:
                                quota_info += "- Input tokens limit exceeded\n"
                            if "requests" in error_msg_lower:
                                quota_info += "- Requests limit exceeded\n"
                    
                    # If this is the last attempt, raise a helpful error
                    if attempt >= max_retries:
                        raise Exception(
                            f"❌ Gemini API quota exceeded after {max_retries + 1} attempts:\n\n"
                            f"{quota_info}"
                            f"\nOriginal error: {error_msg}\n\n"
                            f"💡 Solutions:\n"
                            f"1. **Wait and retry**: The quota resets based on the limit type (minute/day). "
                            f"   Wait at least {retry_delay:.1f} seconds or check https://ai.dev/rate-limit\n"
                            f"2. **Upgrade API key**: Free tier has very low limits. Consider upgrading: "
                            f"https://ai.google.dev/gemini-api/docs/rate-limits\n"
                            f"3. **Reduce API calls**: Each query triggers multiple API calls. "
                            f"   Try simpler queries or increase GEMINI_API_MIN_DELAY\n"
                            f"4. **Check usage**: Monitor your quota at https://ai.dev/rate-limit\n"
                            f"\nThis tool makes a Gemini API call for each invocation. "
                            f"A single user query can trigger 3-5+ API calls (reasoning + tools + synthesis)."
                        ) from e
                    
                    # Wait before retrying with exponential backoff
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⚠️  Gemini API quota error (attempt {attempt + 1}/{max_retries + 1}). "
                          f"Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Not a quota error, re-raise immediately
                    raise

        return {
            "retrieval": response.output_text_str,
            "usage": response.metadata.model_dump(),
        }

