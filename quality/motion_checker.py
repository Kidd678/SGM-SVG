from __future__ import annotations

from defusedxml.ElementTree import fromstring

from schemas import MotionSpec, QualityIssue, VisualSpec


ESSENTIAL_ROLES = {"node", "event", "card", "focal", "focal-node", "process-node"}


def check_motion_plan(
    svg: str, motion: MotionSpec, visual: VisualSpec
) -> tuple[list[QualityIssue], dict[str, int | float | bool]]:
    root = fromstring(svg)
    ids = {element.attrib["id"] for element in root.iter() if element.attrib.get("id")}
    essential_ids = {
        element.attrib["id"]
        for element in root.iter()
        if element.attrib.get("id") and element.attrib.get("data-role") in ESSENTIAL_ROLES
    }
    action_ids = {action.target_id for action in motion.actions}
    missing_ids = sorted(action_ids - ids)
    covered_essential = essential_ids & action_ids
    coverage = len(covered_essential) / len(essential_ids) if essential_ids else 1.0
    beat_orders = {
        action.source_beat_order
        for action in motion.actions
        if action.source_beat_order is not None
    }
    beat_coverage = len(beat_orders) / len(visual.scene_beats) if visual.scene_beats else 1.0
    phases = {action.phase for action in motion.actions}
    issues: list[QualityIssue] = []

    if not motion.geometry_invariant:
        issues.append(
            QualityIssue(
                severity="error",
                category="motion_geometry",
                description="MotionSpec is not marked as geometry invariant.",
                fix_instruction="Use only opacity and stroke-dashoffset animation on permanent layout.",
            )
        )
    if missing_ids:
        issues.append(
            QualityIssue(
                severity="error",
                category="motion_missing_target",
                description=f"Motion actions reference missing SVG IDs: {missing_ids[:5]}",
                fix_instruction="Bind every motion action to an existing semantic SVG element ID.",
            )
        )
    if coverage < 1:
        issues.append(
            QualityIssue(
                severity="warning",
                category="motion_essential_coverage",
                description=f"Motion covers {coverage:.0%} of essential SVG groups.",
                fix_instruction="Add reveal actions for essential groups that are not covered.",
            )
        )
    if motion.unmatched_targets:
        issues.append(
            QualityIssue(
                severity="warning",
                category="motion_unmatched_scene_targets",
                description=(
                    f"{len(motion.unmatched_targets)} scene-beat targets could not be bound by name."
                ),
                fix_instruction="Use stable semantic IDs that correspond to scene-beat target names.",
            )
        )
    if beat_coverage < 1:
        issues.append(
            QualityIssue(
                severity="warning",
                category="motion_scene_beat_coverage",
                description=f"Motion implements {beat_coverage:.0%} of planned scene beats.",
                fix_instruction="Bind each scene beat to at least one distinct semantic SVG group.",
            )
        )

    return issues, {
        "motion_action_count": len(motion.actions),
        "motion_target_count": len(action_ids),
        "motion_essential_count": len(essential_ids),
        "motion_essential_coverage": round(coverage, 3),
        "motion_scene_beat_coverage": round(beat_coverage, 3),
        "motion_unmatched_target_count": len(motion.unmatched_targets),
        "motion_geometry_invariant": motion.geometry_invariant,
        "motion_total_duration": motion.total_duration,
        "motion_phase_count": len(phases),
        "motion_has_entrance_phase": "entrance" in phases,
        "motion_has_emphasis_phase": "emphasis" in phases,
        "motion_has_ambient_phase": "ambient" in phases,
    }
