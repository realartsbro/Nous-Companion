#!/usr/bin/env python3
"""
QA Report Tool for companion recordings.

Loads a recording JSONL file and produces a structured quality report
covering: reactivity stats, latency distribution, hallucination results,
repetition stats, context snapshot analysis, and a timeline summary.

Usage:
    python scripts/qa_report.py <recording.jsonl> [--output report.json] [--quiet]
    python scripts/qa_report.py ~/.hermes/recordings/*.jsonl

Output: Console report (human-readable) and optional JSON file (machine-readable).
"""

import hashlib
import json
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# ── Claim patterns (shared with detect_hallucinations.py) ───────────────────

CLAIM_PATTERNS = {
    "edit/write": __import__("re").compile(
        r"\b(edited|modified|changed|updated|wrote|rewrote|patched|"
        r"fixed|refactored|replaced|deleted|removed|created|added)\b",
        __import__("re").IGNORECASE,
    ),
    "read": __import__("re").compile(
        r"\b(read|looked at|checked|reviewed|examined|inspected|opened|viewed)\b",
        __import__("re").IGNORECASE,
    ),
    "search": __import__("re").compile(
        r"\b(searched|found|located|discovered|hunted|looked for|grep)\b",
        __import__("re").IGNORECASE,
    ),
    "run/execute": __import__("re").compile(
        r"\b(ran|executed|tested|built|compiled|deployed|installed|"
        r"ran the|running)\b",
        __import__("re").IGNORECASE,
    ),
    "browse": __import__("re").compile(
        r"\b(browsed|navigated|opened the page|visited|went to|looked up)\b",
        __import__("re").IGNORECASE,
    ),
}

TOOL_TO_CATEGORY = {
    "write_file": "edit/write", "patch": "edit/write", "file_write": "edit/write",
    "read_file": "read", "file_read": "read",
    "search_files": "search", "web_search": "search", "web_extract": "search",
    "terminal": "run/execute", "shell": "run/execute", "execute_code": "run/execute",
    "bash": "run/execute", "delegate_task": "run/execute",
    "browser_navigate": "browse", "browser_snapshot": "browse", "browser_click": "browse",
}

CATEGORY_SEVERITY = {
    "edit/write": "HIGH", "run/execute": "MEDIUM",
    "search": "LOW", "browse": "LOW", "read": "LOW",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_recording(path: str) -> list[dict]:
    """Parse JSONL file into an ordered event list."""
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def events_by_type(events: list[dict], *types: str) -> list[dict]:
    """Filter events to those with any of the given types."""
    return [e for e in events if e.get("type") in types]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Reactivity stats
# ═══════════════════════════════════════════════════════════════════════════════

def compute_reactivity(events: list[dict]) -> dict:
    """Count input events, quips, suppression events, idle periods."""
    input_events = events_by_type(events, "input_hermes_event")
    quips = events_by_type(events, "output_quip", "output_text")
    suppressed = events_by_type(events, "output_reaction_suppressed")

    # Count suppression reasons
    reasons: dict[str, int] = {}
    for ev in suppressed:
        r = ev.get("suppression_reason", "unknown")
        reasons[r] = reasons.get(r, 0) + 1

    # Idle periods: gaps > 5 minutes between input events
    idle_periods = 0
    prev_ts = None
    for ev in sorted(input_events, key=lambda e: e.get("wall_ts_ms", 0)):
        ts = ev.get("wall_ts_ms", 0) / 1000.0
        if prev_ts is not None and ts - prev_ts > 300:
            idle_periods += 1
        prev_ts = ts

    # Reaction rate: quips per input event
    reaction_rate = len(quips) / max(1, len(input_events)) * 100

    # Suppression reasons breakdown
    suppression_by_reason = {}
    for ev in suppressed:
        r = ev.get("suppression_reason", "unknown")
        if r not in suppression_by_reason:
            suppression_by_reason[r] = {"count": 0, "reaction_kinds": set()}
        suppression_by_reason[r]["count"] += 1
        suppression_by_reason[r]["reaction_kinds"].add(ev.get("reaction_kind", ""))

    # Convert sets to lists for JSON serialization
    for r in suppression_by_reason:
        suppression_by_reason[r]["reaction_kinds"] = sorted(suppression_by_reason[r]["reaction_kinds"])

    return {
        "total_input_events": len(input_events),
        "total_quips": len(quips),
        "reaction_rate_pct": round(reaction_rate, 1),
        "suppressed_count": len(suppressed),
        "suppression_by_reason": suppression_by_reason,
        "idle_periods_gt_5min": idle_periods,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Latency stats
# ═══════════════════════════════════════════════════════════════════════════════

def percentile(values: list[float], pct: float) -> float:
    """Compute the pct-th percentile of a sorted list of values."""
    if not values:
        return 0.0
    k = (len(values) - 1) * pct / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(values):
        return values[f] + c * (values[f + 1] - values[f])
    return values[f]


def compute_latency(events: list[dict]) -> dict:
    """Compute input→text and input→audio latency distributions."""
    input_events = events_by_type(events, "input_hermes_event")
    text_events = events_by_type(events, "output_text")
    audio_events = events_by_type(events, "output_audio")

    # Time-based matching: each output is paired with the most recent
    # preceding input event (within a 60s window)
    text_latencies: list[float] = []
    audio_latencies: list[float] = []

    def nearest_input(ts, events, window_ms=60000):
        best = None
        for e in events:
            ets = e.get("wall_ts_ms", 0)
            if ets <= ts and ts - ets <= window_ms:
                best = ets
            elif ets > ts:
                break
        return ts - best if best is not None else None

    for ev in text_events:
        lat = nearest_input(ev.get("wall_ts_ms", 0), input_events)
        if lat is not None:
            text_latencies.append(lat)

    for ev in audio_events:
        lat = nearest_input(ev.get("wall_ts_ms", 0), input_events)
        if lat is not None:
            audio_latencies.append(lat)

    text_sorted = sorted(text_latencies)
    audio_sorted = sorted(audio_latencies)

    def fmt_ms(vals: list[float]) -> dict:
        if not vals:
            return {"count": 0, "median_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None, "min_ms": None}
        return {
            "count": len(vals),
            "median_ms": round(percentile(vals, 50)),
            "p50_ms": round(percentile(vals, 50)),
            "p95_ms": round(percentile(vals, 95)),
            "max_ms": round(max(vals)),
            "min_ms": round(min(vals)),
        }

    return {
        "input_to_text": fmt_ms(text_sorted),
        "input_to_audio": fmt_ms(audio_sorted),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Hallucination check (inline – same logic as detect_hallucinations.py)
# ═══════════════════════════════════════════════════════════════════════════════

def check_hallucinations(events: list[dict], window: int = 5) -> dict:
    """Cross-reference quip claims against actual tool calls."""
    by_seq: dict[int, dict] = {}
    for ev in events:
        seq = ev.get("seq", -1)
        if seq is not None and seq >= 0:
            by_seq[seq] = ev

    findings: list[dict] = []

    for ev in events:
        etype = ev.get("type", "")
        if etype == "output_quip":
            text = ev.get("quip_text", "")
        elif etype == "output_text":
            text = ev.get("text", "")
        else:
            continue

        if not text:
            continue

        claimed: set[str] = set()
        for category, pattern in CLAIM_PATTERNS.items():
            if pattern.search(text):
                claimed.add(category)

        if not claimed:
            continue

        trigger_seq = ev.get("trigger_event_seq")
        if trigger_seq is None:
            trigger_seq = ev.get("seq", -1)

        surrounding: list[dict] = []
        for seq in range(max(0, trigger_seq - window), trigger_seq + 1):
            if seq in by_seq and by_seq[seq].get("type") == "input_hermes_event":
                surrounding.append(by_seq[seq])

        actual_categories: set[str] = set()
        for sev in surrounding:
            for tool_name in sev.get("context", {}).get("tools", []) or []:
                cat = TOOL_TO_CATEGORY.get(tool_name)
                if cat:
                    actual_categories.add(cat)

        for claim_cat in claimed:
            if claim_cat not in actual_categories:
                severity = CATEGORY_SEVERITY.get(claim_cat, "LOW")
                findings.append({
                    "quip_seq": ev.get("seq"),
                    "quip_text": text[:120],
                    "claimed_category": claim_cat,
                    "confidence": severity,
                })

    by_confidence = {
        "HIGH": len([f for f in findings if f["confidence"] == "HIGH"]),
        "MEDIUM": len([f for f in findings if f["confidence"] == "MEDIUM"]),
        "LOW": len([f for f in findings if f["confidence"] == "LOW"]),
    }

    return {
        "quips_checked": len(events_by_type(events, "output_quip", "output_text")),
        "possible_hallucinations": len(findings),
        "by_confidence": by_confidence,
        "findings": findings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Repetition detection (Gap D)
# ═══════════════════════════════════════════════════════════════════════════════

def check_repetition(events: list[dict], similarity_threshold: float = 0.85) -> dict:
    """Analyze quip text for repetition patterns.

    Detects:
      - Exact duplicates (shouldn't happen — dedup should catch these)
      - Near duplicates via SequenceMatcher ratio > threshold
      - Prefix matches (same first 10 chars)
      - Unique text hash ratio
    """
    quips = [
        {
            "seq": e.get("seq"),
            "text": e.get("text", "") or e.get("quip_text", ""),
            "ts": e.get("wall_ts_ms", 0),
        }
        for e in events
        if e.get("type") in ("output_text", "output_quip")
    ]

    if not quips:
        return {
            "total_quips": 0,
            "exact_duplicates": [],
            "near_duplicates": [],
            "prefix_matches": [],
            "unique_text_hashes": 0,
            "unique_ratio": 1.0,
            "summary": {"unique_ratio": 1.0, "near_duplicate_pairs": 0, "exact_duplicate_pairs": 0},
        }

    # Track unique hashes
    text_hashes: set[str] = set()
    for q in quips:
        h = hashlib.md5(q["text"].encode("utf-8", errors="replace")).hexdigest()
        text_hashes.add(h)

    exact_duplicates: list[dict] = []
    near_duplicates: list[dict] = []
    prefix_matches: list[dict] = []

    # Pairwise comparison within sliding window of 10 quips
    for i in range(len(quips)):
        a_text = quips[i]["text"]
        if not a_text:
            continue
        for j in range(i + 1, min(i + 10, len(quips))):
            b_text = quips[j]["text"]
            if not b_text:
                continue

            # Exact match
            if a_text == b_text:
                exact_duplicates.append({
                    "seq_a": quips[i]["seq"],
                    "seq_b": quips[j]["seq"],
                    "text": a_text[:80],
                    "gap_s": (quips[j]["ts"] - quips[i]["ts"]) / 1000.0,
                })
                continue

            # SequenceMatcher similarity
            ratio = SequenceMatcher(None, a_text, b_text).ratio()
            if ratio >= similarity_threshold:
                near_duplicates.append({
                    "seq_a": quips[i]["seq"],
                    "seq_b": quips[j]["seq"],
                    "text_a": a_text[:80],
                    "text_b": b_text[:80],
                    "similarity": round(ratio, 3),
                    "gap_s": (quips[j]["ts"] - quips[i]["ts"]) / 1000.0,
                })

            # Prefix match (same first 10 chars)
            prefix_a = a_text[:10].strip().lower()
            prefix_b = b_text[:10].strip().lower()
            if len(prefix_a) >= 5 and prefix_a == prefix_b:
                prefix_matches.append({
                    "seq_a": quips[i]["seq"],
                    "seq_b": quips[j]["seq"],
                    "prefix": prefix_a,
                })

    unique_ratio = len(text_hashes) / max(1, len(quips))

    return {
        "total_quips": len(quips),
        "exact_duplicates": exact_duplicates,
        "near_duplicates": near_duplicates,
        "prefix_matches": prefix_matches,
        "unique_text_hashes": len(text_hashes),
        "unique_ratio": round(unique_ratio, 3),
        "summary": {
            "unique_ratio": round(unique_ratio, 3),
            "near_duplicate_pairs": len(near_duplicates),
            "exact_duplicate_pairs": len(exact_duplicates),
            "prefix_match_pairs": len(prefix_matches),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Context stats
# ═══════════════════════════════════════════════════════════════════════════════

def compute_context_stats(events: list[dict]) -> dict:
    """Analyze context_snapshot events."""
    snapshots = events_by_type(events, "context_snapshot")

    if not snapshots:
        return {"context_snapshots": 0}

    brain_prompt_sizes: list[int] = []
    user_prompt_sizes: list[int] = []
    quip_history_counts: list[int] = []

    for sn in snapshots:
        bp = sn.get("brain_system_prompt", "")
        up = sn.get("user_prompt", "")
        qh = sn.get("quip_history_at_time", [])

        if bp:
            brain_prompt_sizes.append(len(bp))
        if up:
            user_prompt_sizes.append(len(up))
        if isinstance(qh, list):
            quip_history_counts.append(len(qh))

    def avg(vals: list[int]) -> float:
        return sum(vals) / len(vals) if vals else 0

    return {
        "context_snapshots": len(snapshots),
        "avg_brain_prompt_size_kb": round(avg(brain_prompt_sizes) / 1024, 1),
        "avg_user_prompt_size_kb": round(avg(user_prompt_sizes) / 1024, 1),
        "avg_quip_history_count": round(avg(quip_history_counts), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Timeline summary
# ═══════════════════════════════════════════════════════════════════════════════

def report_timeline(events: list[dict]) -> list[dict]:
    """Build a compact event timeline."""
    # Get key event types for timeline
    key_types = {
        "input_hermes_event", "output_text", "output_quip", "output_audio",
        "output_reaction_suppressed", "context_snapshot", "system_error",
        "output_start_recording", "output_stop_recording",
    }

    timeline: list[dict] = []
    for ev in events:
        etype = ev.get("type", "")
        if etype not in key_types:
            continue

        entry: dict[str, Any] = {
            "seq": ev.get("seq"),
            "type": etype,
            "wall_ts_ms": ev.get("wall_ts_ms"),
        }

        if etype == "input_hermes_event":
            entry["event_type"] = ev.get("event_type", "")
            tools = ev.get("context", {}).get("tools", [])
            if tools:
                entry["tools"] = tools[:5]
        elif etype in ("output_text", "output_quip"):
            entry["text"] = (ev.get("text") or ev.get("quip_text", ""))[:80]
        elif etype == "output_reaction_suppressed":
            entry["reason"] = ev.get("suppression_reason", "")
        elif etype == "system_error":
            entry["error_type"] = ev.get("error_type", "")
            entry["message"] = (ev.get("message", "") or "")[:100]

        timeline.append(entry)

    return timeline


# ═══════════════════════════════════════════════════════════════════════════════
# Session duration
# ═══════════════════════════════════════════════════════════════════════════════

def compute_session_duration(events: list[dict]) -> str:
    """Compute the session duration from first to last event."""
    if not events:
        return "0s"
    t0 = events[0].get("wall_ts_ms", 0)
    t1 = events[-1].get("wall_ts_ms", 0)
    duration_s = (t1 - t0) / 1000.0
    if duration_s < 60:
        return f"{round(duration_s)}s"
    elif duration_s < 3600:
        return f"{int(duration_s // 60)}m {int(duration_s % 60)}s"
    else:
        h = int(duration_s // 3600)
        m = int((duration_s % 3600) // 60)
        return f"{h}h {m}m"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Report summary
# ═══════════════════════════════════════════════════════════════════════════════

def report_summary(results: dict) -> str:
    """Format and return the full QA report as a string."""
    lines: list[str] = []

    lines.append("=" * 65)
    lines.append("  COMPANION QA REPORT")
    lines.append("=" * 65)
    lines.append(f"  File:           {results.get('file', '?')}")
    lines.append(f"  Session:        {results.get('session_duration', '?')}")
    lines.append(f"  Total Events:   {results.get('total_events', 0)}")
    lines.append("")

    # ── Reactivity ──
    r = results.get("reactivity", {})
    lines.append("─" * 65)
    lines.append("  REACTIVITY")
    lines.append("─" * 65)
    lines.append(f"  Input events:       {r.get('total_input_events', 0)}")
    lines.append(f"  Quips delivered:    {r.get('total_quips', 0)}")
    lines.append(f"  Reaction rate:      {r.get('reaction_rate_pct', 0)}%")
    lines.append(f"  Suppressed events:  {r.get('suppressed_count', 0)}")
    lines.append(f"  Idle periods >5min: {r.get('idle_periods_gt_5min', 0)}")
    # Show top suppression reasons
    by_reason = r.get("suppression_by_reason", {})
    if by_reason:
        lines.append("  Top suppression reasons:")
        for reason in sorted(by_reason, key=lambda k: by_reason[k]["count"], reverse=True)[:5]:
            info = by_reason[reason]
            lines.append(f"    {reason}: {info['count']} ({', '.join(info['reaction_kinds'])})")
    lines.append("")

    # ── Latency ──
    l = results.get("latency", {})
    lines.append("─" * 65)
    lines.append("  LATENCY")
    lines.append("─" * 65)
    for label, data in [("Input → Text", l.get("input_to_text", {})),
                         ("Input → Audio", l.get("input_to_audio", {}))]:
        if data.get("count", 0) > 0:
            lines.append(f"  {label}:")
            lines.append(f"    Count: {data['count']}  "
                         f"Median: {data.get('median_ms', '?')}ms  "
                         f"P95: {data.get('p95_ms', '?')}ms  "
                         f"Max: {data.get('max_ms', '?')}ms")
        else:
            lines.append(f"  {label}: No data")
    lines.append("")

    # ── Hallucination ──
    h = results.get("hallucination", {})
    lines.append("─" * 65)
    lines.append("  HALLUCINATION CHECK")
    lines.append("─" * 65)
    lines.append(f"  Quips checked:        {h.get('quips_checked', 0)}")
    lines.append(f"  Possible issues:      {h.get('possible_hallucinations', 0)}")
    bc = h.get("by_confidence", {})
    lines.append(f"  By confidence:        HIGH={bc.get('HIGH', 0)}  "
                 f"MEDIUM={bc.get('MEDIUM', 0)}  LOW={bc.get('LOW', 0)}")
    for f in h.get("findings", [])[:5]:
        lines.append(f"    [{f['confidence']}] seq={f.get('quip_seq')}: "
                     f"claimed '{f.get('claimed_category')}' — \"{f.get('quip_text', '')[:60]}\"")
    lines.append("")

    # ── Repetition ──
    rep = results.get("repetition", {})
    lines.append("─" * 65)
    lines.append("  REPETITION")
    lines.append("─" * 65)
    rep_sum = rep.get("summary", {})
    lines.append(f"  Quips checked:         {rep.get('total_quips', 0)}")
    lines.append(f"  Unique text hashes:    {rep.get('unique_text_hashes', 0)}")
    lines.append(f"  Unique ratio:          {rep.get('unique_ratio', 1.0)}")
    lines.append(f"  Near-duplicate pairs:  {rep_sum.get('near_duplicate_pairs', 0)}")
    lines.append(f"  Exact duplicate pairs: {rep_sum.get('exact_duplicate_pairs', 0)}")
    lines.append(f"  Prefix matches:        {rep_sum.get('prefix_match_pairs', 0)}")
    for nd in rep.get("near_duplicates", [])[:5]:
        lines.append(f"    seq={nd.get('seq_a')} ↔ seq={nd.get('seq_b')} "
                     f"sim={nd.get('similarity', 0):.3f} "
                     f"gap={nd.get('gap_s', 0):.0f}s "
                     f"\"{nd.get('text_a', '')[:40]}\"")
    lines.append("")

    # ── Context ──
    ctx = results.get("context", {})
    lines.append("─" * 65)
    lines.append("  CONTEXT SNAPSHOTS")
    lines.append("─" * 65)
    lines.append(f"  Snapshots:             {ctx.get('context_snapshots', 0)}")
    lines.append(f"  Avg brain prompt:      {ctx.get('avg_brain_prompt_size_kb', 0)} KB")
    lines.append(f"  Avg user prompt:       {ctx.get('avg_user_prompt_size_kb', 0)} KB")
    lines.append(f"  Avg quip history:      {ctx.get('avg_quip_history_count', 0)} entries")
    lines.append("")

    # ── Timeline ──
    tl = results.get("timeline", [])
    lines.append("─" * 65)
    lines.append("  TIMELINE (key events)")
    lines.append("─" * 65)
    for entry in tl[:50]:
        etype = entry.get("type", "?")
        seq = entry.get("seq", "?")
        detail = ""
        if etype == "input_hermes_event":
            detail = entry.get("event_type", "")
            tools = entry.get("tools", [])
            if tools:
                detail += f" [{', '.join(tools[:3])}]"
        elif etype in ("output_text", "output_quip"):
            detail = entry.get("text", "")
        elif etype == "output_reaction_suppressed":
            detail = f"reason={entry.get('reason', '')}"
        elif etype == "system_error":
            detail = f"{entry.get('error_type', '')}: {entry.get('message', '')}"
        lines.append(f"  [{seq:>4}] {etype:<30} {detail[:60]}")

    if len(tl) > 50:
        lines.append(f"  ... and {len(tl) - 50} more events")

    lines.append("")
    lines.append("=" * 65)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def run_qa(recording_path: str) -> dict:
    """Run all QA checks on a recording and return results dict."""
    events = load_recording(recording_path)

    reactivity = compute_reactivity(events)
    latency = compute_latency(events)
    hallucination = check_hallucinations(events)
    repetition = check_repetition(events)
    context_stats = compute_context_stats(events)
    session_duration = compute_session_duration(events)
    timeline = report_timeline(events)

    return {
        "file": recording_path,
        "session_duration": session_duration,
        "total_events": len(events),
        "reactivity": reactivity,
        "latency": latency,
        "hallucination": hallucination,
        "repetition": repetition,
        "context": context_stats,
        "timeline": timeline,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="QA Report Tool for companion recordings"
    )
    parser.add_argument(
        "recording",
        help="Path to .jsonl recording file",
    )
    parser.add_argument(
        "--output", "-o",
        help="Write JSON report to file",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress console output",
    )
    args = parser.parse_args()

    recording_path = args.recording
    if not Path(recording_path).exists():
        print(f"Error: Recording file not found: {recording_path}", file=sys.stderr)
        sys.exit(1)

    results = run_qa(recording_path)

    if args.output:
        # Remove timeline from JSON output (it's verbose)
        json_results = {k: v for k, v in results.items() if k != "timeline"}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(json_results, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"JSON report written to {args.output}")

    if not args.quiet:
        print(report_summary(results))


if __name__ == "__main__":
    main()
