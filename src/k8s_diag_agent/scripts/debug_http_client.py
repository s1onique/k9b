"""HTTP client for debug diagnostic scripts."""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


class HttpClient:
    """Simple HTTP client for fetching debug data."""
    
    def __init__(
        self,
        timeout: int = 30,
        insecure: bool = False,
        headers: list[str] | None = None,
        token: str | None = None,
        verbose: bool = False,
    ):
        self.timeout = timeout
        self.insecure = insecure
        self.headers = headers or []
        self.token = token
        self.verbose = verbose
    
    def _build_request(self, url: str) -> urllib.request.Request:
        headers_dict = {}
        for header in self.headers:
            if ':' in header:
                name, value = header.split(':', 1)
                headers_dict[name.strip()] = value.strip()
        if self.token:
            headers_dict['Authorization'] = f'Bearer {self.token}'
        return urllib.request.Request(url, headers=headers_dict)
    
    def fetch_json(self, url: str) -> tuple[dict | None, int, str | None]:
        """Fetch JSON from URL. Returns (data, status, error)."""
        if self.verbose:
            print(f"[VERBOSE] Fetching: {url}", file=sys.stderr)
        
        try:
            request = self._build_request(url)
            if self.insecure:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urllib.request.urlopen(request, timeout=self.timeout, context=ctx)
            else:
                response = urllib.request.urlopen(request, timeout=self.timeout)
            
            http_code = response.getcode()
            content = response.read().decode('utf-8')
            
            if self.verbose:
                print(f"[VERBOSE] HTTP Status: {http_code}", file=sys.stderr)
            
            try:
                data = json.loads(content) if content.strip() else {}
            except json.JSONDecodeError as e:
                if self.verbose:
                    print(f"[VERBOSE] Response is not valid JSON: {e}", file=sys.stderr)
                return None, http_code, None
            
            return data, http_code, None
            
        except urllib.error.HTTPError as e:
            if self.verbose:
                print(f"[VERBOSE] HTTP Error: {e.code} {e.reason}", file=sys.stderr)
            return None, e.code, f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            if self.verbose:
                print(f"[VERBOSE] URL Error: {e.reason}", file=sys.stderr)
            return None, 0, f"Connection error: {e.reason}"
        except TimeoutError:
            if self.verbose:
                print(f"[VERBOSE] Timeout after {self.timeout}s", file=sys.stderr)
            return None, 0, f"Timeout after {self.timeout}s"
        except Exception as e:
            if self.verbose:
                print(f"[VERBOSE] Error: {e}", file=sys.stderr)
            return None, 0, str(e)


def fetch_and_save(
    client: HttpClient,
    url: str,
    output_file: Path,
    description: str,
    failed_count: int = 0,
) -> tuple[bool, int]:
    """Fetch JSON and save to file. Returns (success, failed_count)."""
    timestamp = datetime.now(UTC).isoformat()
    print(f"[{timestamp}] Fetching: {description}")
    print(f"[VERBOSE]   URL: {url}", file=sys.stderr)
    print(f"[VERBOSE]   Output: {output_file}", file=sys.stderr)
    
    data, http_code, error = client.fetch_json(url)
    
    if error and http_code == 0:
        print(f"[{datetime.now(UTC).isoformat()}]   FAILED: {error}")
        return False, failed_count + 1
    
    if http_code >= 400:
        print(f"[{datetime.now(UTC).isoformat()}]   HTTP Error: {http_code}")
        output_file.write_text(json.dumps({"error": error or f"HTTP {http_code}"}, indent=2))
        return False, failed_count + 1
    
    if data is not None:
        output_file.write_text(json.dumps(data, indent=2))
        print(f"[{datetime.now(UTC).isoformat()}]   OK: saved to {output_file}")
        return True, failed_count
    else:
        output_file.write_text(json.dumps({}))
        print(f"[{datetime.now(UTC).isoformat()}]   WARNING: Empty response saved")
        return True, failed_count
