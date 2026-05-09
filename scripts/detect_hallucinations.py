#!/usr/bin/env python3
"""
Hallucination detector for companion recordings.

Loads a JSONL recording file and identifies quips where the companion
claimed a tool action that doesn't match the actual tool calls recorded.

The companion's brain prompt instructs it: "If you only READ or SEARCHED
a file, do NOT claim you edited, modified, or changed it." But LLMs
sometimes hallucinate — especially when given rich session context that
mentions files. This regex-based first pass catches obvious fabrications.

Usage:
    python scripts/detect_hallucinations.py <recording.jsonl> [--window N] [--output report.json]
    python scripts/detect_hallucinations.py ~/.hermes/recordings/default_nosessio_nous_2026-05-05T120000Z.jsonl

Known limitations:
    - Regex-only, no semantic understanding. False positives possible (e.g.,
      "I found the bug" could be metaphorical). False negatives guaranteed
      (e.g., "That's done" without an explicit verb).
    - Window-limited. Only checks N preceding input events.
    - No negation handling. "I didn't edit that file" would falsely trigger.
    - No context_snapshot analysis. Doesn't determine if hallucination came
      from stale context vs. model confabulation.
    - Conservative: flags only when claimed category is completely absent
      from surrounding input events.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

# ── Claim patterns ──────────────────────────────────────────────────────────

CLAIM_PATTERNS: dict[str, re.Pattern] = {
    "edit/write": re.compile(
        r"\b(edited|modified|changed|updated|wrote|rewrote|patched|"
        r"fixed|refactored|replaced|deleted|removed|created|added)\b",
        re.IGNORECASE,
    ),
    "read": re.compile(
        r"\b(read|looked at|checked|reviewed|examined|inspected|opened|viewed)\b",
        re.IGNORECASE,
    ),
    "search": re.compile(
        r"\b(searched|found|located|discovered|hunted|looked for|grep)\b",
        re.IGNORECASE,
    ),
    "run/execute": re.compile(
        r"\b(ran|executed|tested|built|compiled|deployed|installed|"
        r"ran the|running)\b",
        re.IGNORECASE,
    ),
    "browse": re.compile(
        r"\b(browsed|navigated|opened the page|visited|went to|looked up)\b",
        re.IGNORECASE,
    ),
}

# ── Tool name → category mapping ────────────────────────────────────────────

TOOL_TO_CATEGORY: dict[str, str] = {
    # edit/write
    "write_file": "edit/write",
    "patch": "edit/write",
    "file_write": "edit/write",
    # read
    "read_file": "read",
    "file_read": "read",
    # search
    "search_files": "search",
    "web_search": "search",
    "web_extract": "search",
    # run/execute
    "terminal": "run/execute",
    "shell": "run/execute",
    "execute_code": "run/execute",
    "bash": "run/execute",
    "delegate_task": "run/execute",
    # browse
    "browser_navigate": "browse",
    "browser_snapshot": "browse",
    "browser_click": "browse",
}

# ── Category severity ───────────────────────────────────────────────────────

CATEGORY_SEVERITY: dict[str, str] = {
    "edit/write": "HIGH",
    "run/execute": "MEDIUM",
    "search": "LOW",
    "browse": "LOW",
    "read": "LOW",
}


def detect_claims(text: str) -> set[str]:
    """Detect which claim categories appear in the quip text."""
    found: set[str] = set()
    for category, pattern in CLAIM_PATTERNS.items():
        if pattern.search(text):
            found.add(category)
    return found


def extract_tool_categories(events: list[dict]) -> set[str]:
    """Extract all tool categories from a list of input_hermes_event events."""
    categories: set[str] = set()
    for event in events:
        tools = event.get("context", {}).get("tools", [])
        if isinstance(tools, list):
            for tool_name in tools:
                cat = TOOL_TO_CATEGORY.get(tool_name)
                if cat:
                    categories.add(cat)
    return categories


def load_recording(path: str) -> list[dict]:
    """Load all events from a JSONL recording file."""
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


def detect(recording_path: str, window: int = 5) -> list[dict]:
    """Run hallucination detection on a recording file."""
    events = load_recording(recording_path)
    findings: list[dict] = []

    # Index by seq for fast lookup
    by_seq: dict[int, dict] = {}
    for ev in events:
        seq = ev.get("seq", -1)
        if seq is not None and seq >= 0:
            by_seq[seq] = ev

    for ev in events:
        etype = ev.get("type", "")

        # Check both output_quip and output_text
        if etype == "output_quip":
            text = ev.get("quip_text", "")
        elif etype == "output_text":
            text = ev.get("text", "")
        else:
            continue

        if not text:
            continue

        claimed = detect_claims(text)
        if not claimed:
            continue

        # Find surrounding input events
        trigger_seq = ev.get("trigger_event_seq")
        if trigger_seq is None:
            # Fall back to using seq to find nearby input events
            trigger_seq = ev.get("seq", -1)

        surrounding: list[dict] = []
        for seq in range(max(0, trigger_seq - window), trigger_seq + 1):
            if seq in by_seq and by_seq[seq].get("type") == "input_hermes_event":
                surrounding.append(by_seq[seq])

        actual_categories = extract_tool_categories(surrounding)

        # Check each claimed category
        for claim_cat in claimed:
            if claim_cat not in actual_categories:
                # Determine confidence
                severity = CATEGORY_SEVERITY.get(claim_cat, "LOW")

                findings.append({
                    "recording": str(Path(recording_path).name),
                    "quip_seq": ev.get("seq"),
                    "quip_text": text,
                    "claimed_category": claim_cat,
                    "actual_categories": sorted(actual_categories),
                    "confidence": severity,
                    "trigger_event_seq": trigger_seq,
                    "surrounding_tools": _collect_tool_names(surrounding),
                })

    return findings


def _collect_tool_names(events: list[dict]) -> list[str]:
    """Collect all unique tool names from input events."""
    tools: set[str] = set()
    for ev in events:
        tool_list = ev.get("context", {}).get("tools", [])
        if isinstance(tool_list, list):
            for t in tool_list:
                tools.add(t)
    return sorted(tools)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect companion hallucinations in recording files"
    )
    parser.add_argument(
        "recording",
        help="Path to .jsonl recording file",
    )
    parser.add_argument(
        "--window", "-w",
        type=int,
        default=5,
        help="Number of preceding input events to check (default: 5)",
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

    findings = detect(recording_path, window=args.window)

    if args.output:
        report = {
            "recording": recording_path,
            "window": args.window,
            "total_findings": len(findings),
            "by_confidence": {
                "HIGH": len([f for f in findings if f["confidence"] == "HIGH"]),
                "MEDIUM": len([f for f in findings if f["confidence"] == "MEDIUM"]),
                "LOW": len([f for f in findings if f["confidence"] == "LOW"]),
            },
            "findings": findings,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"Report written to {args.output}")

    if not args.quiet:
        print(f"\n{'=' * 60}")
        print(f"Hallucination Detection Report: {recording_path}")
        print(f"Window: {args.window} input events | Total findings: {len(findings)}")
        print(f"{'=' * 60}\n")

        for f in findings:
            flag = (
                "🔴" if f["confidence"] == "HIGH"
                else ("🟡" if f["confidence"] == "MEDIUM" else "⚪")
            )
            print(f"{flag} [{f['confidence']}] seq={f['quip_seq']}")
            print(f"   Quip: \"{f['quip_text'][:120]}\"")
            print(f"   Claimed: {f['claimed_category']} | Actual: {f['actual_categories'] or 'none'}")
            print(f"   Surrounding tools: {f['surrounding_tools'] or 'none'}")
            print()

        if not findings:
            print("No hallucinations detected. 🎉")


if __name__ == "__main__":
    main()
