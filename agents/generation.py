from __future__ import annotations

import json
import re
from typing import TypeVar

from defusedxml.ElementTree import fromstring
from pydantic import BaseModel

from core.config import settings
from core.llm_client import V2LLMClient
from core.schemas import MotionPlan, SceneGraph

T = TypeVar("T", bound=BaseModel)


SCENE_SYSTEM = """
You are a semantic scene-graph planner for animated SVG infographics.
Convert the user's request into a compact visual scene graph.

Rules:
- Use XML-safe ids: lowercase letters, numbers, and underscores only.
- Include title, main semantic nodes, connectors when useful, and final emphasis.
- Every important visible idea must have one element with a stable id.
- order defines reading order and animation reveal order.
- Keep labels concise enough to fit inside SVG nodes.
- Detect the visible language from the user's request. If the request is in
  English, set language to "en" and write every label, summary, narrative, and
  style hint in English. If the request is in Chinese, use Chinese.
"""


SVG_SYSTEM = """
You are a senior SVG infographic designer.
Create a polished static SVG from a provided semantic scene graph.

Hard requirements:
- Return only one complete SVG, no Markdown and no commentary.
- Use <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800">.
- Do not include CSS animations; this stage is static only.
- Every scene element must map to one visible <g> with matching id, data-role,
  and data-order. Put related shapes and text inside that group.
- Keep visible text readable, normally 16px or larger.
- Do not use micro-captions. If space is tight, remove secondary text instead
  of shrinking it below 14px.
- Keep all visible content inside the canvas and inside its visual container.
- Avoid external resources, scripts, foreignObject, event handlers, and image tags.
- Prefer visual explanation over prose-heavy blocks.
- For process diagrams with many steps, use a roomy two-row or arc layout instead
  of letting a large focal object overlap the process nodes.
- Use the scene graph language for all visible text. If scene_graph.language is
  "en", every visible label, title, caption, and annotation must be English.
"""


REPAIR_SYSTEM = """
You repair static SVG infographics after browser geometry inspection.

Make a local repair pass only. Keep the same topic, style, ids, data-role values,
and static SVG nature. Do not add animation.

Priorities:
- Remove overlaps between semantic groups.
- Raise all visible text to at least 14px, preferably 16px for body labels.
- If space is tight, shorten or remove secondary captions.
- Keep every scene-graph element represented by a stable group id.
- Preserve the scene graph language for all visible text.
- Return only one complete SVG.
"""


USER_REVISION_SYSTEM = """
You revise static SVG infographics according to a final human edit request.

Make a local revision only. Keep the original topic, scene-graph ids, data-role
values, data-order values, and static SVG nature. Do not add animation.

Follow the human request when it is compatible with the scene graph. If the
request conflicts with readability or safety, choose the closest safe revision.
Preserve the scene graph language for all visible text.
Return only one complete SVG.
"""


MOTION_SYSTEM = """
You are a motion designer for educational SVG infographics.
Create a MotionPlan for the given scene graph.

Rules:
- The title appears first.
- Main nodes appear one by one in scene order.
- Connectors appear after the elements they connect.
- Background elements may stay static or fade in early.
- Final frame must remain complete and readable.
- Use seconds for start and duration.
"""


class SceneGraphAgent:
    def __init__(self, client: V2LLMClient) -> None:
        self.client = client

    def run(self, prompt: str) -> SceneGraph:
        user_prompt = (
            "Create a scene graph for this animated SVG infographic request.\n"
            "Important language rule: visible text must follow the user's prompt "
            "language. English prompt -> English SVG text; Chinese prompt -> "
            "Chinese SVG text.\n\n"
            f"User request:\n{prompt}"
        )
        scene_graph = complete_json_v2(
            self.client,
            SCENE_SYSTEM,
            user_prompt,
            SceneGraph,
            temperature=0.2,
            task_name="版本2语义场景图",
            max_tokens=5000,
        )
        if _looks_english(prompt) and (
            scene_graph.language != "en" or _scene_has_cjk(scene_graph)
        ):
            scene_graph = complete_json_v2(
                self.client,
                SCENE_SYSTEM,
                (
                    f"{user_prompt}\n\n"
                    "The request is English. Set language to en. Do not use any "
                    "Chinese characters in title, narrative, labels, summaries, or "
                    "style_hints."
                ),
                SceneGraph,
                temperature=0.1,
                task_name="版本2英文场景图重试",
                max_tokens=5000,
            )
        return scene_graph


class StaticSvgAgent:
    def __init__(self, client: V2LLMClient) -> None:
        self.client = client

    def run(self, prompt: str, scene_graph: SceneGraph) -> str:
        raw = self.client.complete(
            SVG_SYSTEM,
            (
                "Original user request:\n"
                f"{prompt}\n\n"
                "Semantic scene graph to render:\n"
                f"{scene_graph.model_dump_json(indent=2)}\n\n"
                f"Visible text language: {scene_graph.language}. "
                "Use this language for every visible word in the SVG.\n\n"
                "Return only the static SVG."
            ),
            temperature=0.45,
            max_tokens=settings.svg_max_tokens,
            timeout_seconds=settings.svg_timeout_seconds,
            retry_timeout_seconds=settings.svg_retry_timeout_seconds,
            max_attempts=1,
            task_name="版本2静态SVG生成",
        )
        return validate_svg(raw)

    def repair(self, prompt: str, scene_graph: SceneGraph, svg: str, issues: list[dict]) -> str:
        raw = self.client.complete(
            REPAIR_SYSTEM,
            (
                "Original user request:\n"
                f"{prompt}\n\n"
                "Scene graph that must stay represented:\n"
                f"{scene_graph.model_dump_json(indent=2)}\n\n"
                f"Visible text language: {scene_graph.language}. "
                "Keep every visible word in this language.\n\n"
                "Browser QA issues to fix:\n"
                f"{json.dumps(issues[:6], ensure_ascii=False, indent=2)}\n\n"
                "Previous static SVG:\n"
                f"{svg[:22000]}\n\n"
                "Return only the repaired static SVG."
            ),
            temperature=0.2,
            max_tokens=settings.svg_max_tokens,
            timeout_seconds=settings.svg_timeout_seconds,
            retry_timeout_seconds=settings.svg_retry_timeout_seconds,
            max_attempts=1,
            task_name="版本2静态SVG修复",
        )
        return validate_svg(raw)

    def revise(
        self,
        prompt: str,
        scene_graph: SceneGraph,
        svg: str,
        user_instruction: str,
    ) -> str:
        raw = self.client.complete(
            USER_REVISION_SYSTEM,
            (
                "Original user request:\n"
                f"{prompt}\n\n"
                "Scene graph that must stay represented:\n"
                f"{scene_graph.model_dump_json(indent=2)}\n\n"
                f"Visible text language: {scene_graph.language}. "
                "Keep every visible word in this language unless the human request "
                "explicitly asks for bilingual text.\n\n"
                "Human final revision request:\n"
                f"{user_instruction}\n\n"
                "Current static SVG:\n"
                f"{svg[:24000]}\n\n"
                "Return only the revised static SVG."
            ),
            temperature=0.25,
            max_tokens=settings.svg_max_tokens,
            timeout_seconds=settings.svg_timeout_seconds,
            retry_timeout_seconds=settings.svg_retry_timeout_seconds,
            max_attempts=1,
            task_name="版本2人工修改",
        )
        return validate_svg(raw)


class MotionPlannerAgent:
    def __init__(self, client: V2LLMClient) -> None:
        self.client = client

    def run(self, scene_graph: SceneGraph) -> MotionPlan:
        return complete_json_v2(
            self.client,
            MOTION_SYSTEM,
            (
                "Create a concise MotionPlan for this scene graph:\n"
                f"{scene_graph.model_dump_json(indent=2)}"
            ),
            MotionPlan,
            temperature=0.2,
            task_name="版本2动画计划",
            max_tokens=5000,
        )


def complete_json_v2(
    client: V2LLMClient,
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
    *,
    temperature: float,
    task_name: str,
    max_tokens: int,
) -> T:
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    repair_note = ""
    last_error: Exception | None = None
    for _ in range(2):
        raw = client.complete(
            system_prompt,
            (
                f"{user_prompt}\n\n"
                "Return exactly one valid JSON object matching this JSON Schema. "
                "Do not use Markdown fences or commentary.\n"
                f"{schema_text}"
                f"{repair_note}"
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            task_name=task_name,
            max_attempts=1,
        )
        try:
            return schema.model_validate(_loads_json_object(raw))
        except Exception as exc:
            last_error = exc
            repair_note = (
                "\n\n上一轮 JSON 未通过校验。请只返回修正后的 JSON 对象。"
                f"校验错误：{exc}"
            )
    raise ValueError(f"{task_name} 的 JSON 校验失败：{last_error}")


def _loads_json_object(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("没有找到 JSON 对象")
    return json.loads(text[start : end + 1])


def validate_svg(text: str) -> str:
    svg = extract_svg(text)
    try:
        root = fromstring(svg)
    except Exception:
        repaired = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
            "&amp;",
            svg,
        )
        root = fromstring(repaired)
        svg = repaired
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("根元素必须是 svg")
    return svg


def extract_svg(text: str) -> str:
    text = re.sub(r"^```(?:xml|svg)?\s*|\s*```$", "", text.strip())
    match = re.search(r"<svg\b[\s\S]*?</svg>", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError("模型响应中没有完整 SVG")
    return match.group(0)


def _looks_english(text: str) -> bool:
    ascii_letters = sum(char.isascii() and char.isalpha() for char in text)
    cjk_chars = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return ascii_letters >= 12 and cjk_chars == 0


def _scene_has_cjk(scene_graph: SceneGraph) -> bool:
    text = scene_graph.model_dump_json(ensure_ascii=False)
    return any("\u4e00" <= char <= "\u9fff" for char in text)
