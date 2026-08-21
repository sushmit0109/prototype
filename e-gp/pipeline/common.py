"""
Shared HTTP plumbing for the eGP pipeline.

The portal (eprocure.gov.bd) is a plain JSP app: a JSESSIONID cookie from any
GET authorises everything else, search pages are POST servlets that return an
HTML row fragment (not JSON), and there is no CAPTCHA. This wraps that in one
small client shared by every source crawler: one cookie jar (CookieJar is
internally lock-protected, safe to share across threads), a UA that
identifies the project and links back to it, and a bounded-concurrency rate
limiter -- fast enough that a ~1.1M-tender backfill finishes in a practical
number of scheduled runs, but capped well short of anything that would look
like an attack on a government server: MAX_CONCURRENCY sockets in flight at
once, spaced at least MIN_INTERVAL apart. If a run ever sees a run of 429s or
503s, turn these two constants down before anything else.
"""
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://www.eprocure.gov.bd"
UA = ("Mozilla/5.0 (compatible; egp-dashboard/1.0; "
      "+https://sushmit0109.github.io/prototype/e-gp/)")

MAX_CONCURRENCY = 8      # sockets in flight at once
MIN_INTERVAL = 0.12      # seconds between request starts, aggregate across all threads

_jar = CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_slot_lock = threading.Lock()
_next_slot = 0.0
_inflight = threading.Semaphore(MAX_CONCURRENCY)


def _throttle():
    """Block until this call's turn in a shared, evenly-spaced schedule."""
    global _next_slot
    with _slot_lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + MIN_INTERVAL
    wait = slot - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def bootstrap():
    """GET the homepage once to pick up a session cookie."""
    _throttle()
    req = urllib.request.Request(BASE + "/", headers={"User-Agent": UA})
    with _opener.open(req, timeout=60) as r:
        r.read()


def get(path, retries=4):
    """GET a path under BASE; return the response body as text."""
    last_err = None
    for attempt in range(retries):
        _throttle()
        with _inflight:
            try:
                req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
                with _opener.open(req, timeout=60) as r:
                    return r.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                time.sleep(2 ** attempt)
    raise last_err


def post(path, fields, retries=4):
    """POST to a servlet path under BASE; return the response body as text.

    Safe to call from multiple threads: concurrency is capped at
    MAX_CONCURRENCY and request starts are paced by _throttle regardless of
    how many threads are calling in.
    """
    data = urllib.parse.urlencode(fields).encode()
    last_err = None
    for attempt in range(retries):
        _throttle()
        with _inflight:
            try:
                req = urllib.request.Request(
                    BASE + path, data=data,
                    headers={
                        "User-Agent": UA,
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                with _opener.open(req, timeout=60) as r:
                    return r.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                time.sleep(2 ** attempt)
    raise last_err
