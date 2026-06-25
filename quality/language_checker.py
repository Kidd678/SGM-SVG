from __future__ import annotations

import re

from defusedxml.ElementTree import fromstring

from schemas import QualityIssue


def check_visible_language(svg: str, expected_language: str) -> list[QualityIssue]:
    """Reject Chinese visible copy for explicitly English requests."""
    if expected_language != "en":
        return []
    root = fromstring(svg)
    visible_text = " ".join(
        "".join(element.itertext())
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "text"
    )
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", visible_text))
    if cjk_count == 0:
        return []
    return [
        QualityIssue(
            severity="error",
            category="output_language",
            description=f"英文请求的 SVG 可见文字中仍包含 {cjk_count} 个中文字符。",
            fix_instruction=(
                "将所有可见标题、标签、关系说明、图例和注释改为英文；"
                "平台名称等专有名词使用用户原始英文写法。"
            ),
        )
    ]
