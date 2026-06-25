from __future__ import annotations

import atexit
from pathlib import Path
from threading import Lock, get_ident
from typing import Any


SYSTEM_BROWSER_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

_LOCK = Lock()
_PLAYWRIGHT: Any | None = None
_BROWSER: Any | None = None
_OWNER_THREAD_ID: int | None = None


def new_page(viewport: dict[str, int] | None = None) -> Any:
    """Create a page from a reused headless Chromium instance."""
    global _PLAYWRIGHT, _BROWSER, _OWNER_THREAD_ID
    with _LOCK:
        current_thread_id = get_ident()
        if _OWNER_THREAD_ID is not None and _OWNER_THREAD_ID != current_thread_id:
            # Playwright sync objects are bound to their greenlet/thread. If FastAPI
            # moves the next request to another worker thread, do not reuse them.
            _PLAYWRIGHT = None
            _BROWSER = None
            _OWNER_THREAD_ID = None
        if _BROWSER is None or not _BROWSER.is_connected():
            from playwright.sync_api import sync_playwright

            _PLAYWRIGHT = sync_playwright().start()
            executable = next((path for path in SYSTEM_BROWSER_CANDIDATES if path.exists()), None)
            launch_options: dict[str, Any] = {"headless": True}
            if executable:
                launch_options["executable_path"] = str(executable)
            _BROWSER = _PLAYWRIGHT.chromium.launch(**launch_options)
            _OWNER_THREAD_ID = current_thread_id
        return _BROWSER.new_page(viewport=viewport or {"width": 1200, "height": 800})


def close_browser() -> None:
    global _PLAYWRIGHT, _BROWSER, _OWNER_THREAD_ID
    with _LOCK:
        if _OWNER_THREAD_ID is not None and _OWNER_THREAD_ID != get_ident():
            _BROWSER = None
            _PLAYWRIGHT = None
            _OWNER_THREAD_ID = None
            return
        if _BROWSER is not None:
            try:
                _BROWSER.close()
            finally:
                _BROWSER = None
        if _PLAYWRIGHT is not None:
            try:
                _PLAYWRIGHT.stop()
            finally:
                _PLAYWRIGHT = None
        _OWNER_THREAD_ID = None


atexit.register(close_browser)
