#!/usr/bin/env python3
"""Parse subtitle scripts (VTT/SRT/Markdown) for the translate skill.

Prints cue indices, silence gaps, and scene-break hints:
  82 | gap= 0.000s | 00:10:25.833 --> 00:10:29.750 | 我們一起舒服起來吧？
  83 | gap=13.225s | 00:10:42.975 --> 00:10:47.458 | 不 不行了 已經到極限了 [GAP >= 8s: MUST BREAK]
  85 | gap= 5.825s | 00:10:58.575 --> 00:11:03.625 | 要去了 要去了啊 [GAP 3-8s (5.83s): CHECK TURN]

Can also verify a translated `script_vn.md` against the source (`--verify`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TS_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)"
)
TRACK_RE = re.compile(r"^(?:#\s*\d+|##\s+.+)$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
VOICE_RE = re.compile(r"<v(?:\.[^\s>]*)?\s+([^>]+)>")  # WebVTT speaker span, e.g. <v S2> from `subs transcribe`
LEFTOVER_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\u0e00-\u0e7f\[\]<>]"
)


def parse_time(ts: str) -> float:
    ts = ts.replace(",", ".").strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    m, s = parts
    return int(m) * 60 + float(s)


def parse_source(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    tracks: list[tuple[str, list[dict]]] = []
    cur_title = "Track 1"
    cur_lines: list[str] = []
    has_track_headers = any(TRACK_RE.match(l.strip()) for l in lines)

    if has_track_headers:
        in_track = False
        for line in lines:
            if TRACK_RE.match(line.strip()):
                if in_track:
                    tracks.append((cur_title, _parse_cues_from_lines(cur_lines)))
                cur_title = re.sub(r"^#+\s*", "", line.strip())
                cur_lines = []
                in_track = True
            elif in_track:
                cur_lines.append(line)
        if in_track:
            tracks.append((cur_title, _parse_cues_from_lines(cur_lines)))
    else:
        tracks.append((path.stem, _parse_cues_from_lines(lines)))

    return tracks


def _parse_cues_from_lines(lines: list[str]) -> list[dict]:
    cues = []
    i = 0
    n = len(lines)
    prev_end = None
    while i < n:
        m = TS_RE.match(lines[i])
        if not m:
            i += 1
            continue
        start_str, end_str = m.group(1), m.group(2)
        start_s = parse_time(start_str)
        end_s = parse_time(end_str)
        i += 1
        text_lines = []
        while i < n and lines[i].strip() != "" and not TS_RE.match(lines[i]):
            text_lines.append(HTML_TAG_RE.sub("", VOICE_RE.sub(r"\1: ", lines[i].strip())))
            i += 1
        cue_text = " ".join(t for t in text_lines if t)
        gap = 0.0 if prev_end is None else max(0.0, start_s - prev_end)
        prev_end = end_s
        cues.append(
            {
                "index": len(cues) + 1,
                "start_str": start_str,
                "end_str": end_str,
                "start": start_s,
                "end": end_s,
                "gap": gap,
                "text": cue_text,
            }
        )
    return cues


def parse_translated(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    chapters: list[tuple[str, list[tuple[str, bool]]]] = []
    cur_title = None
    cur_items: list[tuple[str, bool]] = []
    had_blank = False

    for raw in lines:
        s = raw.strip()
        if s.startswith("# ") and not s.startswith("## "):
            continue
        if s.startswith("## ") or re.match(r"^(?:Chương|Track|Part)\s+\d+", s) or re.match(r"^\d+$", s):
            if cur_title is not None:
                chapters.append((cur_title, cur_items))
            cur_title = s
            cur_items = []
            had_blank = False
            continue
        if s == "":
            if cur_items:
                had_blank = True
            continue
        if cur_title is None:
            cur_title = "Chương 1"
        cur_items.append((s, had_blank))
        had_blank = False

    if cur_title is not None:
        chapters.append((cur_title, cur_items))
    return chapters


def cmd_dump(tracks, selected_tracks: set[int] | None, summary_only: bool):
    seen_fingerprints: dict[tuple[str, ...], int] = {}
    print("=== SURVEY ===")
    total_cues = 0
    for idx, (title, cues) in enumerate(tracks, 1):
        total_cues += len(cues)
        fp = tuple(c["text"] for c in cues)
        dup_note = ""
        if fp in seen_fingerprints and fp:
            dup_note = f"  [DUPLICATE of Track {seen_fingerprints[fp]}!]"
        else:
            seen_fingerprints[fp] = idx
        must_breaks = sum(1 for c in cues[1:] if c["gap"] >= 8.0)
        turn_checks = sum(1 for c in cues[1:] if 3.0 <= c["gap"] < 8.0)
        print(
            f"Track {idx}: {title} | {len(cues)} cues | "
            f">=8s breaks: {must_breaks} | 3-8s turns: {turn_checks}{dup_note}"
        )
    print(f"Total: {len(tracks)} tracks, {total_cues} cues")

    if summary_only:
        return

    for idx, (title, cues) in enumerate(tracks, 1):
        if selected_tracks and idx not in selected_tracks:
            continue
        print(f"\n=== Track {idx}: {title} ({len(cues)} cues) ===")
        for c in cues:
            i = c["index"]
            gap = c["gap"]
            tag = ""
            if i > 1:
                if gap >= 8.0:
                    tag = " [GAP >= 8s: MUST BREAK]"
                elif gap >= 3.0:
                    tag = f" [GAP 3-8s ({gap:.2f}s): CHECK TURN]"
            print(
                f"{i:3d} | gap={gap:6.3f}s | {c['start_str']} --> {c['end_str']} | "
                f"{c['text']}{tag}"
            )


def cmd_verify(tracks, vn_path: Path, drop_tracks: set[int]) -> int:
    kept_tracks = [
        (idx, title, cues)
        for idx, (title, cues) in enumerate(tracks, 1)
        if idx not in drop_tracks
    ]
    chapters = parse_translated(vn_path)
    problems = 0

    raw_lines = vn_path.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(raw_lines, 1):
        m = LEFTOVER_RE.search(line)
        if m:
            print(f"[PROBLEM] Line {lineno}: leftover char/bracket {m.group(0)!r}: {line}")
            problems += 1

    if len(chapters) != len(kept_tracks):
        print(
            f"[PROBLEM] Track count mismatch: source has {len(kept_tracks)} kept tracks, "
            f"translation has {len(chapters)} chapters."
        )
        problems += 1

    for (src_idx, src_title, cues), (ch_title, items) in zip(kept_tracks, chapters):
        if len(items) != len(cues):
            print(
                f"[PROBLEM] {ch_title} (Source Track {src_idx}): "
                f"expected {len(cues)} lines, got {len(items)}"
            )
            problems += 1
            continue

        missing_breaks = []
        short_gap_breaks = []
        for c, (vn_line, has_break_before) in zip(cues[1:], items[1:]):
            if c["gap"] >= 8.0 and not has_break_before:
                missing_breaks.append((c["index"], c["gap"], c["text"], vn_line))
            elif c["gap"] < 3.0 and has_break_before:
                short_gap_breaks.append((c["index"], c["gap"], c["text"], vn_line))

        scenes = 1 + sum(1 for _, b in items[1:] if b)
        print(
            f"[OK] {ch_title}: {len(items)}/{len(cues)} lines, {scenes} scenes "
            f"(missing >=8s breaks: {len(missing_breaks)}, <3s breaks: {len(short_gap_breaks)})"
        )
        for cidx, gap, stxt, vtxt in missing_breaks:
            print(f"  [PROBLEM] Cue {cidx} (gap={gap:.2f}s >= 8s) missing blank line before: {vtxt}")
            problems += 1
        for cidx, gap, stxt, vtxt in short_gap_breaks:
            print(f"  [WARN] Cue {cidx} (gap={gap:.2f}s < 3s) has a blank line before: {vtxt}")

    if problems == 0:
        print("\nVerification passed with 0 problems.")
    else:
        print(f"\nVerification found {problems} problem(s).")
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Source subtitle/markdown file")
    ap.add_argument("--track", "-t", type=int, action="append", help="Only print specific track number(s)")
    ap.add_argument("--summary", "-s", action="store_true", help="Only print track survey summary")
    ap.add_argument("--verify", "-v", type=Path, help="Verify a translated script_vn.md against source")
    ap.add_argument("--drop", type=int, action="append", default=[], help="Dropped source track numbers")
    args = ap.parse_args()

    tracks = parse_source(args.source)
    if args.verify:
        sys.exit(cmd_verify(tracks, args.verify, set(args.drop)))
    cmd_dump(tracks, set(args.track) if args.track else None, args.summary)


if __name__ == "__main__":
    main()
