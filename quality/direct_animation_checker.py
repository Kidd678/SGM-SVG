from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from quality.browser_runtime import new_page
from schemas import QualityIssue


def inspect_direct_animation_sequence(svg: str) -> tuple[list[QualityIssue], dict[str, int | float | bool]]:
    html = (
        "<!doctype html><html><style>"
        "html,body{margin:0;background:#fff}svg{width:1200px;height:800px}"
        "</style><body>"
        + svg
        + "</body></html>"
    )
    with TemporaryDirectory() as temp_dir:
        html_path = Path(temp_dir) / "preview.html"
        html_path.write_text(html, encoding="utf-8")
        page = new_page(viewport={"width": 1200, "height": 800})
        try:
            page.goto(html_path.as_uri())
            data = page.evaluate(
                """() => {
                  const semanticSelector = [
                    '[data-role="node"]',
                    '[data-role="event"]',
                    '[data-role="card"]',
                    '[data-role="focal"]',
                    '[data-role="focal-node"]',
                    '[data-role="process-node"]'
                  ].join(',');
                  const blocks = [...document.querySelectorAll(semanticSelector)]
                    .filter(el => {
                      const text = (el.textContent || '').trim();
                      const r = el.getBoundingClientRect();
                      return text && r.width > 1 && r.height > 1;
                    });
                  const animations = document.getAnimations().map(animation => {
                    const target = animation.effect?.target;
                    const timing = animation.effect?.getTiming?.() || {};
                    return {
                      id: target?.id || '',
                      role: target?.dataset?.role || '',
                      delay: Number(timing.delay || 0),
                      duration: Number(timing.duration || 0),
                      name: animation.animationName || ''
                    };
                  });
                  const animationFor = element => {
                    const candidates = animations.filter(item => {
                      if (!item.id) return false;
                      const target = document.getElementById(item.id);
                      return target === element || element.contains(target) || target?.contains(element);
                    });
                    if (!candidates.length) return null;
                    candidates.sort((a, b) => a.delay - b.delay);
                    return candidates[0];
                  };
                  const blockData = blocks.map((block, index) => {
                    const animation = animationFor(block);
                    return {
                      index,
                      id: block.id || '',
                      role: block.dataset.role || '',
                      text: (block.textContent || '').trim().slice(0, 36),
                      delay: animation ? animation.delay : null
                    };
                  });
                  return {
                    blockData,
                    animationCount: animations.length,
                    animatedBlockCount: blockData.filter(item => item.delay !== null).length
                  };
                }"""
            )
        finally:
            page.close()

    blocks = data["blockData"]
    animated_count = data["animatedBlockCount"]
    issues: list[QualityIssue] = []
    metrics: dict[str, int | float | bool] = {
        "direct_animation_count": data["animationCount"],
        "direct_animation_block_count": len(blocks),
        "direct_animation_animated_block_count": animated_count,
        "direct_animation_has_sequence": False,
    }
    if len(blocks) < 3:
        return issues, metrics
    if animated_count < max(3, len(blocks) - 1):
        issues.append(
            QualityIssue(
                severity="error",
                category="animation_sequence_missing",
                description=(
                    f"Only {animated_count}/{len(blocks)} semantic text blocks have reveal "
                    "animations. Important text blocks should appear in logical order."
                ),
                fix_instruction=(
                    "Group each major text block with its visual node and add staggered CSS "
                    "reveal animations in reading order. The final frame must remain complete."
                ),
            )
        )
        return issues, metrics

    delays = [item["delay"] for item in blocks if item["delay"] is not None]
    unique_delays = len({round(delay, 2) for delay in delays})
    out_of_order = any(later < earlier for earlier, later in zip(delays, delays[1:]))
    metrics["direct_animation_unique_delays"] = unique_delays
    metrics["direct_animation_has_sequence"] = unique_delays >= max(3, len(delays) // 2) and not out_of_order
    if unique_delays < max(3, len(delays) // 2) or out_of_order:
        issues.append(
            QualityIssue(
                severity="error",
                category="animation_sequence_flat",
                description=(
                    "Semantic text blocks do not reveal with clearly increasing delays in "
                    "document reading order."
                ),
                fix_instruction=(
                    "Use increasing animation-delay values so the title appears first and "
                    "each major node/text block appears one by one along the logical flow."
                ),
            )
        )
    return issues, metrics
