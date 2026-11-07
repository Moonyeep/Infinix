"""Network utilities for the Infinix agent."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Make an HTTP request and return structured response.
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Optional HTTP headers
        body: Optional request body (string)
        timeout: Request timeout in seconds
    
    Returns:
        Dict with status_code, headers, body, and timing info
    """
    start_time = time.monotonic()
    
    # Validate URL
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    
    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https schemes are allowed, got: {parsed.scheme}")
    
    # Build request
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    
    # Add default headers
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    if "User-Agent" not in (headers or {}):
        req.add_header("User-Agent", "Infinix-Agent/1.6.19")
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = response.read(10_000_000).decode("utf-8", errors="replace")
            elapsed = time.monotonic() - start_time
            
            return {
                "status_code": response.status,
                "headers": dict(response.headers),
                "body": response_body[:1_000_000],  # Cap at 1MB
                "elapsed_seconds": round(elapsed, 3),
                "success": True,
            }
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start_time
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        
        return {
            "status_code": e.code,
            "headers": dict(e.headers) if hasattr(e, 'headers') else {},
            "body": error_body[:10_000],
            "elapsed_seconds": round(elapsed, 3),
            "success": False,
            "error": f"HTTP {e.code}: {e.reason}",
        }
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start_time
        return {
            "status_code": 0,
            "headers": {},
            "body": "",
            "elapsed_seconds": round(elapsed, 3),
            "success": False,
            "error": f"URL Error: {str(e.reason)}",
        }
    except Exception as e:
        elapsed = time.monotonic() - start_time
        return {
            "status_code": 0,
            "headers": {},
            "body": "",
            "elapsed_seconds": round(elapsed, 3),
            "success": False,
            "error": f"{type(e).__name__}: {str(e)[:500]}",
        }


def check_port(host: str, port: int, timeout: int = 5) -> dict[str, Any]:
    """Check if a TCP port is open on a host.
    
    Args:
        host: Hostname or IP address
        port: Port number to check
        timeout: Connection timeout in seconds
    
    Returns:
        Dict with open status and response time
    """
    start_time = time.monotonic()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        elapsed = time.monotonic() - start_time
        sock.close()
        
        return {
            "host": host,
            "port": port,
            "open": result == 0,
            "elapsed_seconds": round(elapsed, 3),
        }
    except Exception as e:
        elapsed = time.monotonic() - start_time
        return {
            "host": host,
            "port": port,
            "open": False,
            "elapsed_seconds": round(elapsed, 3),
            "error": str(e)[:200],
        }
