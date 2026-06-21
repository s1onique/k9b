"""HTTP client for debug diagnostic scripts."""

from __future__ import annotations

import json
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
        """Fetch JSON from URL using curl. Returns (data, status, error)."""
        import subprocess
        import tempfile
        
        if self.verbose:
            print(f"[VERBOSE] Fetching: {url}", file=sys.stderr)
        
        # Use a temp file to capture response body; curl writes status to stdout
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Build curl command that writes body to temp file and status to stdout
            cmd = [
                'curl', '-sS', '-f', '-L',
                '-o', tmp_path,
                '-w', '%{http_code}',
                url
            ]
            
            if self.timeout:
                cmd.extend(['--max-time', str(self.timeout)])
            
            if self.insecure:
                cmd.insert(4, '-k')  # Insert -k after -L
            
            for header in self.headers:
                if ':' in header:
                    name, value = header.split(':', 1)
                    cmd.extend(['-H', f'{name.strip()}: {value.strip()}'])
            
            if self.token:
                cmd.extend(['-H', f'Authorization: Bearer {self.token}'])
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout + 5 if self.timeout else 35,
                )
                
                # Parse HTTP status from stdout
                try:
                    http_code = int(result.stdout.strip())
                except ValueError:
                    if result.stderr:
                        return None, 0, result.stderr.strip()
                    return None, 0, f"Invalid curl output: {result.stdout[:100]}"
                
                if self.verbose:
                    print(f"[VERBOSE] HTTP Status: {http_code}", file=sys.stderr)
                
                if http_code >= 400:
                    return None, http_code, f"HTTP {http_code}"
                
                # Read response body from temp file
                with open(tmp_path) as f:
                    body = f.read()
                
                if not body.strip():
                    return {}, http_code, None
                
                try:
                    data = json.loads(body)
                    return data, http_code, None
                except json.JSONDecodeError as e:
                    if self.verbose:
                        print(f"[VERBOSE] Response is not valid JSON: {e}", file=sys.stderr)
                    return None, http_code, None
                    
            except subprocess.TimeoutExpired:
                if self.verbose:
                    print(f"[VERBOSE] Timeout after {self.timeout}s", file=sys.stderr)
                return None, 0, f"Timeout after {self.timeout}s"
            except FileNotFoundError:
                if self.verbose:
                    print("[VERBOSE] curl not found", file=sys.stderr)
                return None, 0, "curl not found"
            except Exception as e:
                if self.verbose:
                    print(f"[VERBOSE] Error: {e}", file=sys.stderr)
                return None, 0, str(e)
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
