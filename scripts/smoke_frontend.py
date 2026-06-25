from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def find_local_chrome() -> str | None:
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def main() -> None:
    screenshot_path = Path(__file__).resolve().parents[1] / "outputs" / "frontend_smoke.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        chrome_path = find_local_chrome()
        if chrome_path:
            browser = playwright.chromium.launch(
                executable_path=chrome_path,
                headless=True,
            )
        else:
            browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 920})
        page.goto("http://127.0.0.1:8020")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_have_text("动态 SVG 视觉叙事实验室")
        expect(page.locator("#generate")).to_be_visible()
        expect(page.locator("#revisionInput")).to_be_visible()
        expect(page.locator("#reviseBtn")).to_be_visible()
        expect(page.locator("#model option")).not_to_have_count(0)
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()
    print(f"前端冒烟测试通过：{screenshot_path}")


if __name__ == "__main__":
    main()
