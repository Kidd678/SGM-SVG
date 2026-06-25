from __future__ import annotations

from schemas import LayoutDraft, LayoutSpec, LayoutZone


_PROSE_ZONE_HINTS = {
    "overview",
    "concept",
    "intro",
    "introduction",
    "summary",
    "integration",
    "conclusion",
    "recap",
    "legend",
    "caption",
    "terminology",
    "keyword",
}


def _looks_like_prose_zone(zone: LayoutZone) -> bool:
    normalized_id = zone.id.lower().replace("-", "_")
    return any(hint in normalized_id for hint in _PROSE_ZONE_HINTS)


def normalize_layout(draft: LayoutDraft, content_type: str = "") -> LayoutSpec:
    """Convert unreliable model coordinates into deterministic non-overlapping bands."""
    unique: list[LayoutZone] = []
    seen: set[str] = set()
    for index, zone in enumerate(draft.zones):
        zone_id = zone.id.strip() or f"zone_{index + 1}"
        if zone_id in seen:
            zone_id = f"{zone_id}_{index + 1}"
        seen.add(zone_id)
        unique.append(zone.model_copy(update={"id": zone_id}))

    if not unique:
        unique = [
            LayoutZone(id="title", role="title", x=40, y=30, width=1120, height=100),
            LayoutZone(id="main", role="content", x=40, y=150, width=1120, height=500),
            LayoutZone(id="summary", role="summary", x=40, y=670, width=1120, height=70),
        ]

    title_zones = [zone for zone in unique if zone.role == "title"][:1]
    flow_zones = [zone for zone in unique if zone.role != "title"]
    if content_type in {"process", "explanation"}:
        # Mechanism graphics need a few deep panels, not a stack of shallow prose cards.
        mechanism_zones = [zone for zone in flow_zones if not _looks_like_prose_zone(zone)]
        flow_zones = (mechanism_zones or flow_zones)[:2]
    elif len(flow_zones) > 3:
        flow_zones = flow_zones[:3]
    ordered_groups = [
        (title_zones, 40, 30, 1120, 100),
        (flow_zones, 40, 150, 1120, 610),
    ]
    normalized: list[LayoutZone] = []
    for zones, band_x, band_y, band_width, band_height in ordered_groups:
        if not zones:
            continue
        gap = 14 if len(zones) > 1 else 0
        zone_height = (band_height - gap * (len(zones) - 1)) / len(zones)
        for index, zone in enumerate(zones):
            normalized.append(
                LayoutZone(
                    id=zone.id,
                    role="title" if zone.role == "title" else "content",
                    x=band_x,
                    y=round(band_y + index * (zone_height + gap), 2),
                    width=band_width,
                    height=round(zone_height, 2),
                )
            )

    ids = [zone.id for zone in normalized]
    reading_order = [zone_id for zone_id in draft.reading_order if zone_id in ids]
    reading_order.extend(zone_id for zone_id in ids if zone_id not in reading_order)
    focal_zone_id = draft.focal_zone_id if draft.focal_zone_id in ids else next(
        (zone.id for zone in normalized if zone.role == "content"),
        ids[0],
    )
    return LayoutSpec(
        canvas_width=1200,
        canvas_height=800,
        zones=normalized,
        focal_zone_id=focal_zone_id,
        reading_order=reading_order,
        typography=draft.typography,
        palette_roles=draft.palette_roles,
    )
