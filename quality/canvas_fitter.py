from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from quality.browser_runtime import new_page


def fit_canvas_bounds(svg: str, margin: int = 16) -> tuple[str, int]:
    """Move overflowing semantic nodes or standalone text back inside the canvas."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for deterministic canvas fitting.") from exc

    html = (
        "<!doctype html><html><style>"
        "html,body{margin:0;width:1200px;height:800px}svg{width:1200px;height:800px}"
        "</style><body>"
        + svg
        + "</body></html>"
    )
    with TemporaryDirectory() as temp_dir:
        html_path = Path(temp_dir) / "fit.html"
        html_path.write_text(html, encoding="utf-8")
        page = new_page(viewport={"width": 1200, "height": 800})
        try:
            page.goto(html_path.as_uri())
            result = page.evaluate(
                """margin => {
                  const svg = document.querySelector("svg");
                  const semantic = '[data-role="node"],[data-role="event"],[data-role="card"],' +
                    '[data-role="focal"],[data-role="focal-node"],[data-role="process-node"]';
                  const overflow = element => {
                    const r = element.getBoundingClientRect();
                    return r.width > 1 && r.height > 1 &&
                      (r.left < margin || r.top < margin ||
                       r.right > 1200 - margin || r.bottom > 800 - margin);
                  };
                  const candidates = [...svg.querySelectorAll("text"), ...svg.querySelectorAll(semantic)]
                    .filter(overflow)
                    .map(element => element.closest(semantic) || element);
                  const targets = [...new Set(candidates)].filter(target =>
                    !candidates.some(other => other !== target && other.contains(target))
                  );
                  let moved = 0;
                  for (const target of targets) {
                    const r = target.getBoundingClientRect();
                    let dx = 0, dy = 0;
                    if (r.width <= 1200 - margin * 2) {
                      if (r.left < margin) dx = margin - r.left;
                      else if (r.right > 1200 - margin) dx = 1200 - margin - r.right;
                    }
                    if (r.height <= 800 - margin * 2) {
                      if (r.top < margin) dy = margin - r.top;
                      else if (r.bottom > 800 - margin) dy = 800 - margin - r.bottom;
                    }
                    if (Math.abs(dx) < .5 && Math.abs(dy) < .5) continue;
                    const wrapper = document.createElementNS("http://www.w3.org/2000/svg", "g");
                    wrapper.setAttribute("data-auto-fit", "canvas");
                    wrapper.setAttribute("transform", `translate(${dx.toFixed(2)} ${dy.toFixed(2)})`);
                    target.parentNode.insertBefore(wrapper, target);
                    wrapper.appendChild(target);
                    moved++;
                  }
                  return {svg: svg.outerHTML, moved};
                }""",
                margin,
            )
        finally:
            page.close()
    return result["svg"], int(result["moved"])
