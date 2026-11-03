"""Left/right edge sensitivity: the cursor reaches the screen's side only once
the eyes have reached theirs; looking near the middle is unchanged.

Far-left targets (8% from the edge) were estimated at 20-24% on s2/s4/s5, so
the sides were out of reach. Horizontal only: top and bottom targets were
already reached 98% of the time and the curve only added false edge hits.
"""

EDGE_LEVELS = ("off", "low", "medium", "high")

# (trigger, knee) as fractions of the width from a side. Past the knee the cursor
# speeds up, arriving at the side when the estimate reaches the trigger.
# Replayed on s2-s5, off / low / medium / high: edge targets reached within
# 100 px 53/50/59/78%, cursor stuck at a side while aiming further in
# 2.2/3.6/5.2/8.3% of frames.
_ZONES = {"low": (0.05, 0.25), "medium": (0.10, 0.30), "high": (0.15, 0.35)}


def next_edge_level(level: str) -> str:
    return EDGE_LEVELS[(EDGE_LEVELS.index(level) + 1) % len(EDGE_LEVELS)]


def apply_edge_reach(x: float, max_x: float, level: str) -> float:
    """Remap a horizontal screen position in [0, max_x] for ``level``."""
    zone = _ZONES.get(level)
    if zone is None:
        return x
    trigger, knee = zone
    position = x / max_x
    from_side = min(position, 1.0 - position)
    if from_side >= knee:
        return x
    remapped = max(knee * (from_side - trigger) / (knee - trigger), 0.0)
    return (remapped if position < 0.5 else 1.0 - remapped) * max_x
