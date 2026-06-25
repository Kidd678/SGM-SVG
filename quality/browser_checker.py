from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

from quality.browser_runtime import new_page
from schemas import LayoutSpec, QualityIssue


FINAL_FRAME_TIME_MS = 8000


def inspect_final_frame(
    svg: str,
    final_frame_time_ms: int = FINAL_FRAME_TIME_MS,
    expected_layout: LayoutSpec | None = None,
) -> tuple[bytes, list[QualityIssue], dict[str, int | float]]:
    """Render and inspect the final animation frame using real browser geometry."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed; visual review cannot render SVG screenshots."
        ) from exc

    html = (
        "<!doctype html><html><style>"
        "html,body{margin:0;background:#dfe7f2}body{display:grid;place-items:center;"
        "width:1200px;height:800px}svg{width:1200px;height:800px}"
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
            if page.locator("svg").count() != 1:
                raise RuntimeError("浏览器未识别到唯一的标准 SVG 根元素，已阻止错误截图审核")
            geometry = page.evaluate(
                """args => {
                  const target = args.target;
                  for (const animation of document.getAnimations()) {
                    animation.pause();
                    animation.currentTime = target;
                  }
                  const essentialSelector = '[data-role="node"],[data-role="event"],[data-role="card"],[data-role="focal"],[data-role="focal-node"],[data-role="process-node"]';
                  const box = element => {
                    const r = element.getBoundingClientRect();
                    return {id: element.id || "", parentId: element.parentElement?.id || "",
                      tag: element.tagName.toLowerCase(),
                      role: element.dataset.role || element.closest("[data-role]")?.dataset.role || "",
                      ownedByEssential: Boolean(element.closest(essentialSelector)),
                      text: (element.textContent || "").trim(), x:r.x, y:r.y,
                      width:r.width, height:r.height, right:r.right, bottom:r.bottom,
                      fontSize: element.tagName.toLowerCase() === "text"
                        ? parseFloat(getComputedStyle(element).fontSize) || 0 : 0};
                  };
                  const selector = 'svg [data-role="node"],svg [data-role="event"],svg [data-role="card"],svg [data-role="focal"],svg [data-role="focal-node"],svg [data-role="process-node"]';
                  const panels = [...document.querySelectorAll('svg [data-role="panel"]')].map(panel => {
                    const directRects = [...panel.children].filter(
                      child => child.tagName?.toLowerCase() === "rect"
                    ).sort((a,b) => {
                      const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
                      return br.width*br.height - ar.width*ar.height;
                    });
                    const outer = directRects[0] || null;
                    const children = [...panel.querySelectorAll(selector)]
                      .filter(child => child.closest('[data-role="panel"]') === panel)
                      .map(box);
                    const outerBox = outer ? box(outer) : box(panel);
                    const visibleChildren = children.filter(child => child.width > 1 && child.height > 1);
                    const union = visibleChildren.length ? {
                      x: Math.min(...visibleChildren.map(child => child.x)),
                      y: Math.min(...visibleChildren.map(child => child.y)),
                      right: Math.max(...visibleChildren.map(child => child.right)),
                      bottom: Math.max(...visibleChildren.map(child => child.bottom))
                    } : null;
                    return {id: panel.id || "", outer: outerBox, children,
                      utilization: union ? {
                        width: (union.right - union.x) / outerBox.width,
                        height: (union.bottom - union.y) / outerBox.height
                      } : null};
                  });
                  const rowContainers = [...document.querySelectorAll('svg > g[id]')]
                    .filter(group => !['title','defs','semantic-motion'].includes(group.id || ''))
                    .map(group => {
                      const boxOfGroup = box(group);
                      const shapes = [...group.querySelectorAll('rect,circle,ellipse,path,polygon,line,polyline')]
                        .filter(shape => {
                          const r = shape.getBoundingClientRect();
                          const fill = getComputedStyle(shape).fill;
                          const stroke = getComputedStyle(shape).stroke;
                          return r.width > 1 && r.height > 1 &&
                            fill !== 'none' &&
                            !shape.closest('[data-role="relationship"]') &&
                            (shape.dataset.role === 'node' || shape.dataset.role === 'focal' ||
                             shape.dataset.role === 'process-node' || r.width * r.height > 900);
                        })
                        .map(box);
                      const texts = [...group.querySelectorAll('text')].map(box);
                      return {id: group.id || '', group: boxOfGroup, shapes, texts};
                    });
                  const layoutZones = (args.layoutZones || []).map(zone => {
                    const element = document.getElementById(zone.id);
                    return {zone, actual: element ? box(element) : null};
                  });
                  const essentialElements = [...document.querySelectorAll(selector)];
                  const connectors = [...document.querySelectorAll('svg path,svg line,svg polyline')]
                    .filter(connector =>
                      connector.hasAttribute('marker-end') ||
                      connector.closest('[data-role="relationship"]')
                    )
                    .map(connector => {
                      if (typeof connector.getTotalLength !== 'function') return null;
                      const length = connector.getTotalLength();
                      if (!Number.isFinite(length) || length < 300) return null;
                      const matrix = connector.getScreenCTM();
                      if (!matrix) return null;
                      const crossed = new Set();
                      for (let index = 3; index <= 17; index++) {
                        const point = connector.getPointAtLength(length * index / 20);
                        const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix);
                        for (const essential of essentialElements) {
                          if (essential.contains(connector) || connector.contains(essential)) continue;
                          if (
                            essential.tagName.toLowerCase() === 'rect' &&
                            essential.dataset.role === 'card'
                          ) continue;
                          const r = essential.getBoundingClientRect();
                          const inset = 5;
                          if (
                            screen.x > r.left + inset && screen.x < r.right - inset &&
                            screen.y > r.top + inset && screen.y < r.bottom - inset
                          ) crossed.add(essential.id || essential.dataset.role || 'unnamed');
                        }
                      }
                      return {id: connector.id || "", crossed: [...crossed]};
                    })
                    .filter(Boolean);
                  return {
                    texts: [...document.querySelectorAll("svg text")].map(box),
                    essentials: [...document.querySelectorAll(selector)].map(box),
                    panels,
                    layoutZones,
                    rowContainers,
                    connectors,
                    containers: [...document.querySelectorAll(selector)].map(group => {
                      const directRects = [...group.children].filter(
                        child => child.tagName?.toLowerCase() === "rect"
                      ).sort((a,b) => {
                        const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
                        return br.width*br.height - ar.width*ar.height;
                      });
                      const markedFrame = directRects.find(rect => rect.dataset.role === "frame");
                      const framedRoles = new Set([
                        "card", "node", "event", "focal", "focal-node", "process-node"
                      ]);
                      const outer = markedFrame || (framedRoles.has(group.dataset.role)
                        ? directRects[0] || null : null);
                      const ownedTexts = [...group.querySelectorAll("text")].filter(text =>
                        text.closest(selector) === group
                      ).map(box);
                      return {id: group.id || "", role: group.dataset.role || "",
                        outer: outer ? box(outer) : null,
                        texts: ownedTexts,
                        ownedShapeCount: [...group.querySelectorAll("rect,circle,ellipse,path,polygon,line,polyline")]
                          .filter(shape => shape.closest(selector) === group).length};
                    })
                  };
                }""",
                {
                    "target": final_frame_time_ms,
                    "layoutZones": (
                        [zone.model_dump() for zone in expected_layout.zones]
                        if expected_layout
                        else []
                    ),
                },
            )
            image = page.screenshot(type="png")
        finally:
            page.close()
    issues = _geometry_issues(geometry)
    metrics = {
        "final_text_count": len(geometry["texts"]),
        "final_essential_count": len(geometry["essentials"]),
        "final_container_count": len(geometry["containers"]),
        "final_panel_count": len(geometry["panels"]),
        "minimum_font_size": min(
            (item["fontSize"] for item in geometry["texts"] if item["fontSize"] > 0),
            default=0,
        ),
        "geometry_error_count": sum(issue.severity == "error" for issue in issues),
        "layout_penalty": _layout_penalty(issues),
        "final_frame_time_ms": final_frame_time_ms,
    }
    return image, issues, metrics


def capture_keyframes(svg: str) -> list[bytes]:
    """Compatibility helper; visual review now intentionally uses only the final frame."""
    image, _, _ = inspect_final_frame(svg)
    return [image]


def _geometry_issues(geometry: dict) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    texts = [item for item in geometry["texts"] if item["width"] > 1 and item["height"] > 1]
    essentials = [
        item for item in geometry["essentials"] if item["width"] > 1 and item["height"] > 1
    ]
    essential_overlaps = []
    for index, first in enumerate(essentials):
        for second in essentials[index + 1 :]:
            if not first["id"] or not second["id"]:
                continue
            first_contains_second = (
                first["x"] <= second["x"] + 1
                and first["y"] <= second["y"] + 1
                and first["right"] >= second["right"] - 1
                and first["bottom"] >= second["bottom"] - 1
            )
            second_contains_first = (
                second["x"] <= first["x"] + 1
                and second["y"] <= first["y"] + 1
                and second["right"] >= first["right"] - 1
                and second["bottom"] >= first["bottom"] - 1
            )
            if first_contains_second or second_contains_first:
                continue
            width = min(first["right"], second["right"]) - max(first["x"], second["x"])
            height = min(first["bottom"], second["bottom"]) - max(first["y"], second["y"])
            if width <= 0 or height <= 0:
                continue
            overlap_area = width * height
            smaller_area = min(
                first["width"] * first["height"], second["width"] * second["height"]
            )
            if smaller_area > 0 and overlap_area / smaller_area >= 0.12:
                essential_overlaps.append((first["id"], second["id"]))
    if essential_overlaps:
        issues.append(
            QualityIssue(
                severity="error",
                category="essential_overlap",
                description=(
                    f"Final frame contains {len(essential_overlaps)} overlapping essential "
                    f"node pairs: {essential_overlaps[:5]}"
                ),
                fix_instruction=(
                    "Reposition or resize essential nodes so their visual bounding boxes do not "
                    "overlap. Preserve at least 16px whitespace between neighboring nodes."
                ),
            )
        )
    panel_overflows = []
    for panel in geometry["panels"]:
        outer = panel["outer"]
        for child in panel["children"]:
            tolerance = 6
            if (
                child["x"] < outer["x"] - tolerance
                or child["y"] < outer["y"] - tolerance
                or child["right"] > outer["right"] + tolerance
                or child["bottom"] > outer["bottom"] + tolerance
            ):
                panel_overflows.append((panel["id"], child["id"]))
    if panel_overflows:
        issues.append(
            QualityIssue(
                severity="error",
                category="panel_content_overflow",
                description=(
                    f"Final frame contains {len(panel_overflows)} essential nodes outside their "
                    f"panel boundaries: {panel_overflows[:5]}"
                ),
                fix_instruction=(
                    "Keep every process node fully inside its assigned panel with at least 16px "
                    "inner padding. Resize or rearrange panel contents instead of overflowing."
                ),
            )
        )
    underused_panels = []
    for panel in geometry["panels"]:
        utilization = panel.get("utilization")
        if (
            utilization
            and len(panel["children"]) >= 3
            and (
                utilization["width"] < 0.72
                or utilization["height"] < 0.52
            )
        ):
            underused_panels.append(
                (
                    panel["id"],
                    round(utilization["width"], 2),
                    round(utilization["height"], 2),
                )
            )
    if underused_panels:
        issues.append(
            QualityIssue(
                severity="error",
                category="underused_panel_space",
                description=(
                    "Core process content leaves excessive empty space in its panel. "
                    f"Panel utilization (id, width, height): {underused_panels[:4]}"
                ),
                fix_instruction=(
                    "Enlarge and redistribute the process nodes to use the available panel. "
                    "Target at least 75% width and 55% height utilization while preserving "
                    "clear spacing and avoiding overlap."
                ),
            )
        )
    underused_rows = []
    for row in geometry.get("rowContainers", []):
        group = row["group"]
        shapes = [
            shape
            for shape in row["shapes"]
            if shape["width"] > 1
            and shape["height"] > 1
            and shape["width"] * shape["height"] > 900
        ]
        if group["width"] >= 500 and group["height"] >= 80 and shapes:
            union_left = min(shape["x"] for shape in shapes)
            union_right = max(shape["right"] for shape in shapes)
            used_width = (union_right - union_left) / group["width"]
            if used_width < 0.32:
                underused_rows.append((row["id"], round(used_width, 2)))
    if len(underused_rows) >= 2:
        issues.append(
            QualityIssue(
                severity="error",
                category="underused_chart_space",
                description=(
                    "Chart rows use too little horizontal space for their main data marks: "
                    f"{underused_rows[:5]}"
                ),
                fix_instruction=(
                    "For statistics or comparison charts, expand the main proportional bars "
                    "or marks across the available row width. Use a shared baseline and let "
                    "the largest value occupy at least 70% of the content width; do not compress "
                    "all bars into the left edge."
                ),
            )
        )
    covered_texts = []
    for row in geometry.get("rowContainers", []):
        for text in row["texts"]:
            if not text["text"]:
                continue
            for shape in row["shapes"]:
                if shape["id"] == text["id"]:
                    continue
                width = min(text["right"], shape["right"]) - max(text["x"], shape["x"])
                height = min(text["bottom"], shape["bottom"]) - max(text["y"], shape["y"])
                if width <= 0 or height <= 0:
                    continue
                overlap_area = width * height
                text_area = text["width"] * text["height"]
                if text_area > 0 and overlap_area / text_area >= 0.35:
                    covered_texts.append((row["id"], text["text"][:24]))
                    break
    if covered_texts:
        issues.append(
            QualityIssue(
                severity="error",
                category="label_obscured_by_mark",
                description=(
                    f"Visible labels are obscured by chart marks or node shapes: {covered_texts[:5]}"
                ),
                fix_instruction=(
                    "Move labels outside filled data marks or add enough contrast and padding. "
                    "Every entity name and ratio label must be fully readable in the final frame."
                ),
            )
        )
    layout_violations = []
    missing_layout_zones = []
    for item in geometry["layoutZones"]:
        zone = item["zone"]
        actual = item["actual"]
        if not actual:
            missing_layout_zones.append(zone["id"])
            continue
        tolerance = 20
        if (
            actual["x"] < zone["x"] - tolerance
            or actual["y"] < zone["y"] - tolerance
            or actual["right"] > zone["x"] + zone["width"] + tolerance
            or actual["bottom"] > zone["y"] + zone["height"] + tolerance
        ):
            layout_violations.append(zone["id"])
    if layout_violations or missing_layout_zones:
        issues.append(
            QualityIssue(
                severity="error",
                category="layout_spec_violation",
                description=(
                    "SVG does not follow the deterministic LayoutSpec. "
                    f"Out-of-zone groups: {layout_violations[:5]}; "
                    f"missing zone groups: {missing_layout_zones[:5]}"
                ),
                fix_instruction=(
                    "Use each LayoutSpec zone ID as the corresponding top-level SVG group ID. "
                    "Keep the complete group inside its assigned x/y/width/height bounds. "
                    "Do not replace stacked zones with side-by-side panels or invent geometry."
                ),
            )
        )
    connector_crossings = [
        (item["id"], target)
        for item in geometry["connectors"]
        for target in item["crossed"]
    ]
    if connector_crossings:
        issues.append(
            QualityIssue(
                severity="error",
                category="connector_node_crossing",
                description=(
                    f"Final frame contains {len(connector_crossings)} connector paths crossing "
                    f"unrelated essential nodes: {connector_crossings[:6]}"
                ),
                fix_instruction=(
                    "Reroute arrows and feedback loops through empty whitespace. Connect only "
                    "at node edges and never pass through an unrelated process node."
                ),
            )
        )
    top_left_texts = [
        item for item in texts if item["x"] < 170 and item["y"] < 170 and item["role"] != "title"
    ]
    orphan_edge_texts = [
        item
        for item in texts
        if not item.get("ownedByEssential")
        and item["role"] not in {"title", "subtitle", "section"}
        and (item["x"] > 900 or item["y"] > 650)
        and len(item["text"]) >= 4
    ]
    if len(orphan_edge_texts) >= 2:
        examples = [item["text"][:24] for item in orphan_edge_texts[:4]]
        issues.append(
            QualityIssue(
                severity="error",
                category="orphan_edge_text",
                description=(
                    f"Final frame contains {len(orphan_edge_texts)} standalone text lines "
                    f"at the right or bottom edge: {examples}"
                ),
                fix_instruction=(
                    "Remove standalone keyword, summary, legend, bullet-list, and footer text. "
                    "Embed each explanation inside its corresponding process node or relationship."
                ),
            )
        )
    text_heavy_containers = []
    for container in geometry["containers"]:
        owned_texts = [item for item in container["texts"] if item["text"]]
        owned_characters = sum(len(item["text"]) for item in owned_texts)
        if len(owned_texts) >= 3 and owned_characters >= 48:
            text_heavy_containers.append(
                (container["id"], len(owned_texts), owned_characters)
            )
    if text_heavy_containers:
        issues.append(
            QualityIssue(
                severity="error",
                category="text_heavy_container",
                description=(
                    "Final frame contains prose-heavy overview, recap, or explanation cards: "
                    f"{text_heavy_containers[:4]}"
                ),
                fix_instruction=(
                    "Delete prose-heavy cards. Express the mechanism with visibly changing "
                    "states, short labels, and arrows; keep at most two short text lines per node."
                ),
            )
        )
    if len(top_left_texts) >= 3:
        issues.append(
            QualityIssue(
                severity="error",
                category="top_left_cluster",
                description=f"最终帧有 {len(top_left_texts)} 个文本集中在左上角，疑似布局 transform 被动画覆盖。",
                fix_instruction="不要用 CSS transform 动画覆盖负责永久定位的 transform；将标签保留在对应节点附近。",
            )
        )
    out_of_bounds = [
        item
        for item in texts
        if item["x"] < -2 or item["y"] < -2 or item["right"] > 1202 or item["bottom"] > 802
    ]
    if out_of_bounds:
        examples = [(item["id"], item["text"][:24]) for item in out_of_bounds[:3]]
        issues.append(
            QualityIssue(
                severity="error",
                category="text_overflow",
                description=f"最终帧有 {len(out_of_bounds)} 个文本超出画布边界。示例：{examples}",
                fix_instruction="调整文本坐标、字号或换行，使所有文字完全位于 1200x800 画布内。",
            )
        )
    title_overflows = [
        item
        for item in texts
        if item["role"] == "title" and (item["x"] < 40 or item["right"] > 1160)
    ]
    if title_overflows:
        examples = [item["text"][:48] for item in title_overflows[:3]]
        issues.append(
            QualityIssue(
                severity="error",
                category="title_overflow",
                description=f"Title text is too wide or too close to the canvas edge: {examples}",
                fix_instruction=(
                    "Shorten the title and keep it fully inside the canvas with at least 40px "
                    "left and right margin. Move descriptive wording to the subtitle instead "
                    "of reducing font size below the required title size."
                ),
            )
        )
    essential_out_of_bounds = [
        item
        for item in essentials
        if item["x"] < -2 or item["y"] < -2 or item["right"] > 1202 or item["bottom"] > 802
    ]
    if essential_out_of_bounds:
        examples = [(item["id"], item["role"]) for item in essential_out_of_bounds[:3]]
        issues.append(
            QualityIssue(
                severity="error",
                category="essential_overflow",
                description=f"最终帧有 {len(essential_out_of_bounds)} 个重要图形节点超出画布。示例：{examples}",
                fix_instruction="整体缩放或重新定位对应重要节点，确保节点完整位于 1200x800 画布内。",
            )
        )
    overlaps = []
    for index, first in enumerate(texts):
        for second in texts[index + 1 :]:
            width = min(first["right"], second["right"]) - max(first["x"], second["x"])
            height = min(first["bottom"], second["bottom"]) - max(first["y"], second["y"])
            if width <= 0 or height <= 0:
                continue
            overlap_area = width * height
            smaller_area = min(
                first["width"] * first["height"], second["width"] * second["height"]
            )
            if smaller_area > 0 and overlap_area / smaller_area >= 0.2:
                overlaps.append((first["text"][:16], second["text"][:16]))
    if overlaps:
        issues.append(
            QualityIssue(
                severity="error",
                category="text_overlap",
                description=f"最终帧检测到 {len(overlaps)} 组明显文字重叠。",
                fix_instruction="重新分配标签坐标或缩短文本，确保最终帧所有文本边界框互不重叠。",
            )
        )
    container_overflows = []
    for container in geometry["containers"]:
        outer = container["outer"]
        if not outer:
            continue
        for text in container["texts"]:
            tolerance = 3
            text_center_x = (text["x"] + text["right"]) / 2
            text_center_y = (text["y"] + text["bottom"]) / 2
            belongs_inside_frame = (
                container["role"] == "card"
                or
                outer["x"] <= text_center_x <= outer["right"]
                and outer["y"] <= text_center_y <= outer["bottom"]
            )
            if not belongs_inside_frame:
                continue
            if (
                text["x"] < outer["x"] - tolerance
                or text["y"] < outer["y"] - tolerance
                or text["right"] > outer["right"] + tolerance
                or text["bottom"] > outer["bottom"] + tolerance
            ):
                container_overflows.append((container["id"], text["text"][:24]))
    if container_overflows:
        issues.append(
            QualityIssue(
                severity="error",
                category="container_overflow",
                description=(
                    f"最终帧有 {len(container_overflows)} 段文字超出所属卡片或节点边界。"
                    f"示例：{container_overflows[:3]}"
                ),
                fix_instruction="保留当前视觉风格，缩短或换行溢出文字，并扩大或重新定位对应容器；禁止缩小字号。",
            )
        )
    tiny_texts = [item for item in texts if 0 < item["fontSize"] < 14]
    if tiny_texts:
        examples = [(item["text"][:20], item["fontSize"]) for item in tiny_texts[:5]]
        issues.append(
            QualityIssue(
                severity="error",
                category="font_too_small",
                description=f"最终帧有 {len(tiny_texts)} 段文字小于 14px。示例：{examples}",
                fix_instruction="保留构图和视觉隐喻，将所有可见文字提高到至少 14px；正文至少 16px，空间不足时删减次要文案或扩大容器。",
            )
        )
    small_body_texts = [
        item for item in texts if item["role"] == "body" and 0 < item["fontSize"] < 16
    ]
    if small_body_texts:
        issues.append(
            QualityIssue(
                severity="error",
                category="body_font_too_small",
                description=f"最终帧有 {len(small_body_texts)} 段正文小于 16px。",
                fix_instruction="将 data-role='body' 的正文提高到至少 16px，并通过删减、换行或扩大容器保持版面整洁。",
            )
        )
    if len(essentials) < 3:
        issues.append(
            QualityIssue(
                severity="error",
                category="missing_essential_nodes",
                description=f"最终帧仅检测到 {len(essentials)} 个重要可视节点，主体内容可能缺失。",
                fix_instruction="为每个核心实体添加 data-role='node/event/card/focal'，并确保最终帧可见。",
            )
        )
    if len(essentials) >= 3:
        clustered = [item for item in essentials if item["x"] < 190 and item["y"] < 190]
        if len(clustered) >= max(3, len(essentials) // 2):
            issues.append(
                QualityIssue(
                    severity="error",
                    category="essential_cluster",
                    description="多数重要节点聚集在左上角，最终布局不可用。",
                    fix_instruction="保留节点原始 translate 定位，动画只改变 opacity，或动画内部子元素。",
                )
            )
    return issues


def _layout_penalty(issues: list[QualityIssue]) -> int:
    weights = {
        "text_overflow": 100,
        "essential_overflow": 100,
        "top_left_cluster": 100,
        "essential_cluster": 100,
        "missing_essential_nodes": 100,
        "text_overlap": 50,
        "container_overflow": 40,
        "font_too_small": 20,
        "body_font_too_small": 20,
        "orphan_edge_text": 80,
        "text_heavy_container": 80,
        "essential_overlap": 100,
        "panel_content_overflow": 100,
        "layout_spec_violation": 120,
        "connector_node_crossing": 100,
        "underused_panel_space": 60,
        "underused_chart_space": 90,
        "label_obscured_by_mark": 70,
        "title_overflow": 100,
    }
    penalty = 0
    for issue in issues:
        if issue.severity != "error":
            continue
        match = re.search(r"(?:有|检测到|仅检测到)\s*(\d+)", issue.description)
        count = max(1, int(match.group(1))) if match else 1
        penalty += weights.get(issue.category, 25) * count
    return penalty
