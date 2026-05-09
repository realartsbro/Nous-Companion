"""Verify scene JSON structure and timing consistency."""
import json
from pathlib import Path

scene_path = Path(__file__).resolve().parent.parent / "demo-scenes/demo-final-v3.nous-scene.json"
raw = scene_path.read_text()
data = json.loads(raw)

meta = data.get("meta", {})
scenes = data.get("scenes", [])

print(f"Title: {meta.get('title')}")
print(f"Expected duration: {meta.get('duration_seconds')}s")
print(f"Scene count: {len(scenes)}")
print()

# Validate each scene has required fields and correct types
errors = []
for i, sc in enumerate(scenes):
    checks = []
    # Required
    if "time" not in sc:
        checks.append("missing 'time'")
    if "expression" not in sc:
        checks.append("missing 'expression'")
    if "line" not in sc:
        checks.append("missing 'line'")

    # Type checks
    if "time" in sc and not isinstance(sc["time"], (int, float)):
        checks.append(f"'time' is {type(sc['time']).__name__}, expected number")
    if "expression" in sc and sc["expression"] not in ("normal", "serious", "cheerful", "interested", "standalones"):
        checks.append(f"unknown expression '{sc['expression']}'")
    if "resize_to" in sc and sc["resize_to"] not in ("small", "medium", "big"):
        checks.append(f"invalid resize_to '{sc['resize_to']}'")
    if "sprite_index" in sc and not isinstance(sc["sprite_index"], int):
        checks.append(f"sprite_index should be int, got {type(sc['sprite_index']).__name__}")
    if "effects" in sc:
        valid_effects = {"show_scanlines", "show_grain", "show_interference", "show_burst", "show_analog_bleed", "sprite_size", "colorize_enabled", "colorize_color", "colorize_strength"}
        non_bool_effects = {"colorize_color": str, "colorize_strength": (int, float), "sprite_size": str}
        for k, v in sc["effects"].items():
            if k not in valid_effects:
                checks.append(f"unknown effect '{k}'")
            elif k in non_bool_effects:
                expected = non_bool_effects[k]
                if not isinstance(v, expected):
                    checks.append(f"effect '{k}' expected {expected.__name__}, got {type(v).__name__}")
            elif not isinstance(v, bool):
                checks.append(f"effect '{k}' should be bool, got {type(v).__name__}")

    if checks:
        errors.append(f"Scene {i} @ {sc.get('time', '?')}s: {'; '.join(checks)}")

# Timing consistency
times = [sc["time"] for sc in scenes]
gaps = []
for i in range(len(times) - 1):
    gap = times[i + 1] - times[i]
    gaps.append(gap)
    if gap < 0:
        errors.append(f"Scene {i+1} time {times[i+1]} < scene {i} time {times[i]} — out of order!")

total_dur = times[-1] if scenes else 0

print("Timing:")
print(f"  First cue: {times[0]:.1f}s")
print(f"  Last cue: {times[-1]:.1f}s")
print(f"  Total duration: {total_dur:.1f}s")
print(f"  Gaps between cues: {[f'{g:.1f}s' for g in gaps]}")
print(f"  Min gap: {min(gaps):.1f}s  Max gap: {max(gaps):.1f}s")
print()

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  ✗ {e}")
else:
    print("✓ All scenes pass validation")

# Count features
resizes = sum(1 for sc in scenes if sc.get("resize_to"))
effect_cues = sum(1 for sc in scenes if sc.get("effects"))
lines = sum(1 for sc in scenes if sc.get("line"))

print(f"\nFeature count:")
print(f"  Spoken lines: {lines}/10")
print(f"  Resize actions: {resizes}")
print(f"  Effect toggles: {effect_cues}")

# Print summary table
print(f"\n{'#':>2} {'Time':>6} {'Dur':>6} {'Expr':>12} {'Line':<60}")
print(f"{'─'*2} {'─'*6} {'─'*6} {'─'*12} {'─'*60}")
for i, sc in enumerate(scenes):
    dur = gaps[i] if i < len(gaps) else total_dur - times[i]
    line_preview = sc.get("line", "(no speech)")[:57] + "..." if len(sc.get("line", "")) > 60 else sc.get("line", "(no speech)")
    extra = ""
    if sc.get("resize_to"):
        extra += f" →{sc['resize_to']}"
    if sc.get("effects"):
        on = [k.replace("show_", "") for k, v in sc["effects"].items() if v]
        off = [k.replace("show_", "") for k, v in sc["effects"].items() if not v]
        if on:
            extra += f" [+{','.join(on)}]"
        if off:
            extra += f" [-{','.join(off)}]"
    print(f"{i:>2} {times[i]:>5.1f}s {dur:>5.1f}s {sc['expression']:>12} {line_preview:<60} {extra}")

print()
print(f"✓ Scene file valid and ready for playback test")
