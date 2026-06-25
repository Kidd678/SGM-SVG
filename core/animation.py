from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from core.schemas import MotionPlan, MotionStep, SceneGraph

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)


def build_default_motion_plan(scene_graph: SceneGraph) -> MotionPlan:
    steps: list[MotionStep] = []
    current = 0.0
    for element in sorted(scene_graph.elements, key=lambda item: item.order):
        if element.role == "background":
            effect = "fade"
            start = 0.0
            duration = 0.4
        elif element.role == "connector":
            effect = "draw-line"
            start = current + 0.15
            duration = 0.55
        elif element.role == "focal":
            effect = "pop"
            start = current
            duration = 0.55
        elif element.importance == "primary":
            effect = "fade-slide"
            start = current
            duration = 0.55
        else:
            effect = "fade-slide"
            start = current
            duration = 0.45
        steps.append(
            MotionStep(
                target_id=element.id,
                effect=effect,
                start=round(start, 2),
                duration=duration,
                reason=f"Reveal {element.label} according to scene order.",
            )
        )
        if element.role != "background":
            current += 0.55
    return MotionPlan(
        total_duration=round(max((s.start + s.duration for s in steps), default=1), 2),
        steps=steps,
    )


def inject_motion(svg: str, motion_plan: MotionPlan) -> str:
    root = ET.fromstring(svg)
    _remove_old_motion_style(root)
    style = ET.Element(_tag("style"), {"id": "v2-motion-style"})
    style.text = "\n" + _build_css(motion_plan) + "\n"
    root.insert(0, style)
    return ET.tostring(root, encoding="unicode")


def _build_css(motion_plan: MotionPlan) -> str:
    lines = [
        "@keyframes v2FadeSlide { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }",
        "@keyframes v2Pop { 0% { opacity: 0; transform: scale(.92); } 70% { opacity: 1; transform: scale(1.03); } 100% { opacity: 1; transform: scale(1); } }",
        "@keyframes v2Fade { from { opacity: 0; } to { opacity: 1; } }",
        "@keyframes v2Draw { from { opacity: 1; stroke-dashoffset: 900; } to { opacity: 1; stroke-dashoffset: 0; } }",
        "@keyframes v2Highlight { 0% { opacity: 0; } 40% { opacity: 1; filter: brightness(1.18); } 100% { opacity: 1; filter: brightness(1); } }",
    ]
    for step in motion_plan.steps:
        selector = f"#{_css_escape_id(step.target_id)}"
        animation = _animation_name(step.effect)
        extra = ""
        if step.effect == "draw-line":
            extra = " stroke-dasharray: 900; stroke-dashoffset: 900;"
        lines.append(
            (
                f"{selector} {{ opacity: 0; transform-box: fill-box; "
                f"transform-origin: center;{extra} "
                f"animation: {animation} {step.duration:.2f}s ease forwards; "
                f"animation-delay: {step.start:.2f}s; }}"
            )
        )
    return "\n".join(lines)


def _animation_name(effect: str) -> str:
    return {
        "fade-slide": "v2FadeSlide",
        "pop": "v2Pop",
        "draw-line": "v2Draw",
        "highlight": "v2Highlight",
        "fade": "v2Fade",
    }.get(effect, "v2FadeSlide")


def _css_escape_id(value: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", value):
        return value
    return "".join(f"\\{ord(char):x} " for char in value)


def _remove_old_motion_style(root: ET.Element) -> None:
    for child in list(root):
        if child.tag.rsplit("}", 1)[-1] == "style" and child.attrib.get("id") == "v2-motion-style":
            root.remove(child)


def _tag(name: str) -> str:
    return f"{{{SVG_NAMESPACE}}}{name}"
