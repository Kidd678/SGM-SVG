from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from core.config import PROJECT_ROOT, V2_ROOT

if str(V2_ROOT) in sys.path:
    sys.path.remove(str(V2_ROOT))
sys.path.insert(0, str(V2_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from agents.generation import MotionPlannerAgent, SceneGraphAgent, StaticSvgAgent
from core.animation import build_default_motion_plan, inject_motion
from core.llm_client import V2LLMClient
from core.schemas import MotionPlan, SceneGraph, V2Metrics, V2Result
from quality.browser_checker import inspect_final_frame
from quality.direct_animation_checker import inspect_direct_animation_sequence
from quality.sanitizer import sanitize_svg


class V2Pipeline:
    def __init__(
        self,
        model_id: str | None = None,
        output_dir: Path | None = None,
        progress_callback: object | None = None,
    ) -> None:
        self.model_id = model_id or "minimax-m2.5"
        self.client = V2LLMClient(self.model_id)
        self.scene_agent = SceneGraphAgent(self.client)
        self.svg_agent = StaticSvgAgent(self.client)
        self.motion_agent = MotionPlannerAgent(self.client)
        self.output_dir = output_dir or V2_ROOT / "outputs"
        self.progress_callback = progress_callback

    def run(
        self,
        prompt: str,
        *,
        use_llm_motion: bool = True,
        repair_static: bool = True,
    ) -> V2Result:
        started = time.perf_counter()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._emit("scene_start", {"message": "正在规划语义场景图"})
        scene_graph = self.scene_agent.run(prompt)
        self._emit("scene_done", {"result": scene_graph.model_dump()})

        self._emit("svg_start", {"message": "正在生成静态 SVG"})
        static_svg = self.svg_agent.run(prompt, scene_graph)
        static_svg = sanitize_svg(static_svg)
        self._emit("svg_done", {"message": "静态 SVG 生成完成"})

        motion_plan: MotionPlan
        if use_llm_motion:
            try:
                self._emit("motion_start", {"message": "正在规划动画"})
                motion_plan = self.motion_agent.run(scene_graph)
                self._emit("motion_done", {"result": motion_plan.model_dump()})
            except Exception:
                motion_plan = build_default_motion_plan(scene_graph)
                self._emit(
                    "motion_done",
                    {"result": motion_plan.model_dump(), "fallback": True},
                )
        else:
            motion_plan = build_default_motion_plan(scene_graph)
            self._emit(
                "motion_done",
                {"result": motion_plan.model_dump(), "deterministic": True},
            )

        self._emit("qa_start", {"message": "正在注入动画并进行浏览器质检"})
        animated_svg = sanitize_svg(inject_motion(static_svg, motion_plan))
        image, geometry_issues, geometry_metrics = inspect_final_frame(animated_svg)
        animation_issues, animation_metrics = inspect_direct_animation_sequence(animated_svg)
        self._emit(
            "qa_done",
            {
                "geometry_error_count": geometry_metrics.get("geometry_error_count", 0),
                "animation_error_count": sum(
                    issue.severity == "error" for issue in animation_issues
                ),
            },
        )

        if repair_static and any(issue.severity == "error" for issue in geometry_issues):
            self._emit("repair_start", {"message": "正在根据浏览器反馈修复静态 SVG"})
            static_svg = self.svg_agent.repair(
                prompt,
                scene_graph,
                static_svg,
                [issue.model_dump() for issue in geometry_issues],
            )
            static_svg = sanitize_svg(static_svg)
            animated_svg = sanitize_svg(inject_motion(static_svg, motion_plan))
            image, geometry_issues, geometry_metrics = inspect_final_frame(animated_svg)
            animation_issues, animation_metrics = inspect_direct_animation_sequence(animated_svg)
            self._emit(
                "repair_done",
                {
                    "geometry_error_count": geometry_metrics.get("geometry_error_count", 0),
                    "animation_error_count": sum(
                        issue.severity == "error" for issue in animation_issues
                    ),
                },
            )

        return self._save_result(
            prompt=prompt,
            scene_graph=scene_graph,
            motion_plan=motion_plan,
            animated_svg=animated_svg,
            image=image,
            geometry_issues=geometry_issues,
            geometry_metrics=geometry_metrics,
            animation_issues=animation_issues,
            animation_metrics=animation_metrics,
            elapsed_override=round(time.perf_counter() - started, 2),
        )

    def revise(
        self,
        *,
        prompt: str,
        scene_graph: SceneGraph,
        motion_plan: MotionPlan,
        current_svg: str,
        user_instruction: str,
    ) -> V2Result:
        started = time.perf_counter()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._emit("revision_start", {"message": "正在根据人工意见修改当前 SVG"})

        static_svg = self.svg_agent.revise(
            prompt,
            scene_graph,
            current_svg,
            user_instruction,
        )
        static_svg = sanitize_svg(static_svg)
        animated_svg = sanitize_svg(inject_motion(static_svg, motion_plan))
        image, geometry_issues, geometry_metrics = inspect_final_frame(animated_svg)
        animation_issues, animation_metrics = inspect_direct_animation_sequence(animated_svg)

        self._emit(
            "revision_done",
            {
                "geometry_error_count": geometry_metrics.get("geometry_error_count", 0),
                "animation_error_count": sum(
                    issue.severity == "error" for issue in animation_issues
                ),
            },
        )

        return self._save_result(
            prompt=prompt,
            scene_graph=scene_graph,
            motion_plan=motion_plan,
            animated_svg=animated_svg,
            image=image,
            geometry_issues=geometry_issues,
            geometry_metrics=geometry_metrics,
            animation_issues=animation_issues,
            animation_metrics=animation_metrics,
            elapsed_override=round(time.perf_counter() - started, 2),
            suffix="人工修改",
            extra_payload={"human_revision": user_instruction},
        )

    def _save_result(
        self,
        *,
        prompt: str,
        scene_graph: SceneGraph,
        motion_plan: MotionPlan,
        animated_svg: str,
        image: bytes,
        geometry_issues: list,
        geometry_metrics: dict,
        animation_issues: list,
        animation_metrics: dict,
        elapsed_override: float | None = None,
        suffix: str = "",
        extra_payload: dict | None = None,
    ) -> V2Result:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        slug = _slug(prompt)
        suffix_part = f"_{suffix}" if suffix else ""
        svg_path = self.output_dir / f"{stamp}_{slug}{suffix_part}.svg"
        png_path = self.output_dir / f"{stamp}_{slug}{suffix_part}.png"
        json_path = self.output_dir / f"{stamp}_{slug}{suffix_part}.json"
        svg_path.write_text(animated_svg, encoding="utf-8")
        png_path.write_bytes(image)

        issues = [issue.model_dump() for issue in [*geometry_issues, *animation_issues]]
        metrics = V2Metrics(
            elapsed_seconds=elapsed_override or 0,
            geometry_error_count=int(geometry_metrics.get("geometry_error_count", 0)),
            animation_error_count=sum(issue.severity == "error" for issue in animation_issues),
            minimum_font_size=float(geometry_metrics.get("minimum_font_size", 0)),
            final_text_count=int(geometry_metrics.get("final_text_count", 0)),
            total_issues=len(issues),
        )
        result = V2Result(
            prompt=prompt,
            model_id=self.model_id,
            scene_graph=scene_graph,
            motion_plan=motion_plan,
            metrics=metrics,
            svg_path=str(svg_path),
            png_path=str(png_path),
            json_path=str(json_path),
            issues=issues,
        )
        payload = result.model_dump()
        payload["browser_metrics"] = geometry_metrics
        payload["animation_metrics"] = animation_metrics
        if extra_payload:
            payload.update(extra_payload)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def _emit(self, event: str, data: dict) -> None:
        if self.progress_callback:
            self.progress_callback(event, data)


def _slug(prompt: str, max_len: int = 36) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in prompt).strip("_")
    return (cleaned or "svg")[:max_len]
