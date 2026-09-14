"""
Small HTTP helper for the public NIFC and Census services.

Why this exists: Python 3.13 enables OpenSSL's strict X.509 checks by
default. On the Hiscox network, TLS is re-signed by a corporate inspection
proxy whose intermediate certificate lacks the "critical" Basic Constraints
flag, so strict mode rejects census.gov and (intermittently) the NIFC
ArcGIS host with "Basic Constraints of CA cert not marked critical".
We clear VERIFY_X509_STRICT for our outbound calls. Certificates are still
verified against the machine's trusted CA store and hostname checking stays
on; only the extra strictness introduced in 3.13 is relaxed.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "HiscoxCatastropheMonitor/0.3 (internal underwriting tool)"
DEFAULT_TIMEOUT = 60


class NetError(RuntimeError):
    """Raised for any transport, HTTP or service-level error. Message is user-readable."""


def _context_for(url: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()  # system CA store, CERT_REQUIRED, check_hostname=True
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def get_bytes(url: str, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context_for(url)) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code} from {urllib.parse.urlparse(url).hostname}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise NetError(f"Could not reach {urllib.parse.urlparse(url).hostname}: {e.reason}") from e
    except TimeoutError as e:
        raise NetError(f"Timed out after {timeout}s contacting {urllib.parse.urlparse(url).hostname}") from e


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    raw = get_bytes(url, params, timeout)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200].decode("utf-8", "replace")
        raise NetError(f"Non-JSON response from {urllib.parse.urlparse(url).hostname}: {snippet!r}") from e
    # ArcGIS returns HTTP 200 with an "error" object on failures.
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise NetError(f"Service error from {urllib.parse.urlparse(url).hostname}: {msg}")
    return data
