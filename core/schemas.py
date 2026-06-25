from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SceneElement(BaseModel):
    id: str = Field(
        description="Stable XML-safe id, for example title, step_1, arrow_1."
    )
    role: Literal[
        "title",
        "subtitle",
        "focal",
        "process-node",
        "event",
        "card",
        "connector",
        "annotation",
        "background",
    ]
    label: str = Field(description="Visible label text, concise and display-ready.")
    summary: str = Field(description="What this element should communicate visually.")
    order: int = Field(description="Reading and reveal order, starting at 0.")
    importance: Literal["primary", "secondary", "supporting"] = "secondary"
    connects: list[str] = Field(
        default_factory=list,
        description="Element ids this element connects to or depends on.",
    )


class SceneGraph(BaseModel):
    title: str
    language: Literal["zh", "en", "mixed"] = "zh"
    visual_type: Literal[
        "process",
        "timeline",
        "comparison",
        "architecture",
        "cycle",
        "concept",
        "dashboard",
    ]
    narrative: str = Field(description="One-sentence visual story for the infographic.")
    elements: list[SceneElement] = Field(min_length=3)
    style_hints: list[str] = Field(default_factory=list)


class MotionStep(BaseModel):
    target_id: str
    effect: Literal[
        "fade-slide",
        "pop",
        "draw-line",
        "highlight",
        "fade",
    ] = "fade-slide"
    start: float = Field(ge=0, description="Animation start time in seconds.")
    duration: float = Field(gt=0, le=3, description="Animation duration in seconds.")
    reason: str = Field(description="Why this timing supports the explanation.")


class MotionPlan(BaseModel):
    total_duration: float = Field(gt=0)
    steps: list[MotionStep] = Field(min_length=3)
    final_frame_rule: str = "All semantic content remains visible and readable."


class V2Metrics(BaseModel):
    elapsed_seconds: float
    geometry_error_count: int = 0
    animation_error_count: int = 0
    minimum_font_size: float = 0
    final_text_count: int = 0
    total_issues: int = 0


class V2Result(BaseModel):
    prompt: str
    model_id: str
    scene_graph: SceneGraph
    motion_plan: MotionPlan
    metrics: V2Metrics
    svg_path: str
    png_path: str
    json_path: str
    issues: list[dict]
