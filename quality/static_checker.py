from __future__ import annotations

import re

from defusedxml.ElementTree import fromstring

from schemas import QualityIssue, QualityReport


def check_svg(svg: str, allow_animation: bool = True) -> QualityReport:
    issues: list[QualityIssue] = []
    metrics: dict[str, int | float | str | bool] = {}

    if not svg.lstrip().startswith("<svg"):
        issues.append(
            QualityIssue(
                severity="error",
                category="renderability",
                description="SVG 字符串不是以标准 <svg> 根元素开头，网页无法正确渲染。",
                fix_instruction="输出标准 <svg xmlns=\"http://www.w3.org/2000/svg\"> 根元素，禁止 ns0:svg 前缀。",
            )
        )

    try:
        root = fromstring(svg)
    except Exception as exc:
        return QualityReport(
            passed=False,
            score=0,
            issues=[
                QualityIssue(
                    severity="error",
                    category="syntax",
                    description=f"SVG cannot be parsed: {exc}",
                    fix_instruction="Return valid XML with one complete svg root.",
                )
            ],
        )

    view_box = root.attrib.get("viewBox", "")
    if view_box != "0 0 1200 800":
        issues.append(
            QualityIssue(
                severity="error",
                category="canvas",
                description=f"Unexpected viewBox: {view_box or 'missing'}",
                fix_instruction='Use viewBox="0 0 1200 800".',
            )
        )

    ids: list[str] = []
    text_count = 0
    visible_text_characters = 0
    shape_count = 0
    animated = False
    for element in root.iter():
        if "id" in element.attrib:
            ids.append(element.attrib["id"])
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "text":
            text_count += 1
            visible_text_characters += len("".join(element.itertext()).strip())
        if tag in {"path", "rect", "circle", "ellipse", "polygon", "line", "polyline"}:
            shape_count += 1
        if tag in {"animate", "animateMotion", "animateTransform", "set"}:
            animated = True
        if tag == "style" and element.text and (
            "@keyframes" in element.text or re.search(r"\banimation(?:-name)?\s*:", element.text)
        ):
            animated = True

    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        issues.append(
            QualityIssue(
                severity="error",
                category="duplicate_id",
                description=f"Duplicate IDs: {', '.join(duplicates[:8])}",
                fix_instruction="Make every SVG id unique.",
            )
        )
    if text_count < 3:
        issues.append(
            QualityIssue(
                severity="warning",
                category="content",
                description="Too little visible explanatory text.",
                fix_instruction="Add a concise title and essential explanatory labels.",
            )
        )
    if text_count > 26:
        issues.append(
            QualityIssue(
                severity="error",
                category="excessive_text_count",
                description=f"SVG contains {text_count} visible text elements, which is too dense.",
                fix_instruction=(
                    "Reduce visible text to at most 24 concise labels. Remove overview, recap, "
                    "summary, terminology, and repeated explanatory copy; show the mechanism "
                    "through visual states and arrows instead."
                ),
            )
        )
    if visible_text_characters > 360:
        issues.append(
            QualityIssue(
                severity="error",
                category="excessive_visible_copy",
                description=(
                    f"SVG contains {visible_text_characters} visible text characters, "
                    "which reads like prose rather than an infographic."
                ),
                fix_instruction=(
                    "Shorten labels and remove repeated prose. Keep only the title, phase "
                    "headings, state labels, and indispensable relationship annotations."
                ),
            )
        )
    if shape_count < 8:
        issues.append(
            QualityIssue(
                severity="warning",
                category="visual_richness",
                description="The SVG contains too few visual shapes.",
                fix_instruction="Use meaningful visual elements and relationships, not text alone.",
            )
        )
    if re.search(r"<(?:script|foreignObject|image)\b|\son\w+\s*=", svg, re.I):
        issues.append(
            QualityIssue(
                severity="error",
                category="security",
                description="Unsafe SVG content detected.",
                fix_instruction="Remove scripts, event handlers, foreignObject and images.",
            )
        )
    if animated and not allow_animation:
        issues.append(
            QualityIssue(
                severity="error",
                category="unexpected_static_animation",
                description="Static SVG contains animation before MotionSpec compilation.",
                fix_instruction="Remove CSS keyframes, animation declarations, and SMIL animation tags.",
            )
        )

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = len(issues) - error_count
    score = max(0, 100 - error_count * 25 - warning_count * 8)
    metrics.update(
        {
            "text_count": text_count,
            "visible_text_characters": visible_text_characters,
            "shape_count": shape_count,
            "id_count": len(ids),
            "animated": animated,
            "error_count": error_count,
            "warning_count": warning_count,
        }
    )
    return QualityReport(
        passed=error_count == 0 and score >= 80,
        score=score,
        issues=issues,
        metrics=metrics,
    )
