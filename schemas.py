from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Entity(BaseModel):
    id: str
    name: str
    description: str = ""


class Relationship(BaseModel):
    source: str
    target: str
    type: str
    label: str = ""


class Quantity(BaseModel):
    expression: str
    normalized: str
    assumption: str = ""


class Event(BaseModel):
    time: str
    event: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = ""


class ContentSpec(BaseModel):
    topic: str
    title: str
    subtitle: str = ""
    content_type: Literal["comparison", "process", "timeline", "explanation", "statistics"]
    core_message: str = ""
    mechanism_steps: list[str] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    quantities: list[Quantity] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    narrative_flow: list[str] = Field(default_factory=list)
    facts_to_show: list[str] = Field(default_factory=list)
    language: Literal["zh", "en"] = "zh"


class SceneBeat(BaseModel):
    order: int
    meaning: str
    targets: list[str] = Field(default_factory=list)
    motion: str


class VisualSpec(BaseModel):
    concept: str
    viz_type: str
    composition: str
    focal_element: str
    background: str
    palette: list[str]
    style_keywords: list[str]
    layout_guidance: list[str]
    scene_beats: list[SceneBeat]


class LayoutZone(BaseModel):
    id: str
    role: Literal["title", "content", "summary", "legend", "caption"]
    x: float = Field(ge=0, le=1200)
    y: float = Field(ge=0, le=800)
    width: float = Field(gt=0, le=1200)
    height: float = Field(gt=0, le=800)


class LayoutSpec(BaseModel):
    canvas_width: int = 1200
    canvas_height: int = 800
    zones: list[LayoutZone] = Field(default_factory=list)
    focal_zone_id: str
    reading_order: list[str] = Field(default_factory=list)
    typography: dict[str, int] = Field(default_factory=dict)
    palette_roles: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_zones(self) -> "LayoutSpec":
        ids = [zone.id for zone in self.zones]
        if len(ids) != len(set(ids)):
            raise ValueError("Layout zone IDs must be unique")
        if set(ids) != set(self.reading_order):
            raise ValueError("reading_order must contain every layout zone ID exactly once")
        if self.focal_zone_id not in ids:
            raise ValueError("focal_zone_id must reference a layout zone")
        for zone in self.zones:
            if zone.x + zone.width > self.canvas_width or zone.y + zone.height > self.canvas_height:
                raise ValueError(f"Layout zone {zone.id} exceeds the canvas")
        for index, first in enumerate(self.zones):
            for second in self.zones[index + 1 :]:
                overlap_width = min(first.x + first.width, second.x + second.width) - max(
                    first.x, second.x
                )
                overlap_height = min(first.y + first.height, second.y + second.height) - max(
                    first.y, second.y
                )
                if overlap_width > 0 and overlap_height > 0:
                    raise ValueError(f"Layout zones {first.id} and {second.id} overlap")
        return self


class LayoutZoneDraft(BaseModel):
    id: str = ""
    role: Literal["title", "content", "summary", "legend", "caption"] = "content"


class LayoutDraft(BaseModel):
    canvas_width: int = 1200
    canvas_height: int = 800
    zones: list[LayoutZoneDraft] = Field(default_factory=list)
    focal_zone_id: str = ""
    reading_order: list[str] = Field(default_factory=list)
    typography: dict[str, int] = Field(default_factory=dict)
    palette_roles: dict[str, str] = Field(default_factory=dict)


class VisualLayoutDraft(BaseModel):
    visual: VisualSpec
    layout: LayoutDraft


class VisualLayoutPlan(BaseModel):
    visual: VisualSpec
    layout: LayoutSpec


class MotionAction(BaseModel):
    target_id: str
    phase: Literal["entrance", "emphasis", "ambient"] = "entrance"
    effect: Literal["reveal", "emphasize", "draw", "flow"]
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    purpose: str = ""
    source_beat_order: int | None = None


class MotionSpec(BaseModel):
    total_duration: float = Field(gt=0)
    actions: list[MotionAction] = Field(default_factory=list)
    unmatched_targets: list[str] = Field(default_factory=list)
    geometry_invariant: bool = True


class DesignBrief(BaseModel):
    content: ContentSpec
    visual: VisualSpec


class QualityIssue(BaseModel):
    severity: Literal["error", "warning"]
    category: str
    element_id: str = ""
    description: str
    fix_instruction: str


class QualityReport(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[QualityIssue] = Field(default_factory=list)
    metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)


class VisualReview(BaseModel):
    score: int = Field(ge=0, le=100)
    readable: bool
    visually_polished: bool
    animation_helpful: bool
    summary: str
    issues: list[QualityIssue] = Field(default_factory=list)


class GenerationResult(BaseModel):
    prompt: str
    content_spec: ContentSpec
    visual_spec: VisualSpec
    layout_spec: LayoutSpec
    motion_spec: MotionSpec
    svg: str
    quality: QualityReport
    repair_rounds: int
