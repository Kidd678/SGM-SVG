from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring


FORBIDDEN_TAGS = {"script", "foreignObject", "iframe", "image", "audio", "video"}
URL_PATTERN = re.compile(r"url\(\s*['\"]?\s*(?:https?:|//)", re.IGNORECASE)
IMPORT_PATTERN = re.compile(r"@import\s+[^;]+;", re.IGNORECASE)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)


def sanitize_svg(svg: str) -> str:
    root = fromstring(svg)
    if _local_name(root.tag) != "svg":
        raise ValueError("Root element must be svg")

    _clean_element(root)
    serialized = ET.tostring(root, encoding="unicode")
    if not serialized.lstrip().startswith("<svg"):
        raise ValueError("清洗后的内容没有序列化为标准 <svg> 根元素")
    return serialized


def _clean_element(element: ET.Element) -> None:
    for child in list(element):
        if _local_name(child.tag) in FORBIDDEN_TAGS:
            element.remove(child)
        else:
            _clean_element(child)

    for name, value in list(element.attrib.items()):
        local = _local_name(name).lower()
        if local.startswith("on") or local in {"href", "xlink:href"}:
            del element.attrib[name]
        elif URL_PATTERN.search(value):
            del element.attrib[name]

    if _local_name(element.tag) == "style" and element.text:
        element.text = IMPORT_PATTERN.sub("", element.text)
        element.text = URL_PATTERN.sub("none", element.text)


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]
