#!/usr/bin/env python3
"""Chunk a Dockxer transcript into overlapping windows for AI agent summarization.

Splits large meeting transcripts (.md converted from Teams .docx by Dockxer) into
overlapping chunks with speaker-turn boundary snapping. Each chunk includes a metadata
header with line range, time range, and overlap info. Designed as a preprocessing step
before feeding chunks to parallel AI subagents for summarization.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Matches a speaker turn line with a timestamp.
# Examples:
#   ![40](<assets/transcript-avatars/avatar_hash.png>)**Speaker Name** 0:03
#   ![40](<assets/transcript-avatars/avatar_hash.png>) **Speaker Name** 1:39:16
# Does NOT match "started transcription" / "stopped transcription" lines.
TURN_PATTERN = re.compile(
    r"^!\[[^\]]*\]"  # ![alt]
    r"\(<[^>]+>\)"  # (<image_path>)
    r"\s*\*\*([^*]+)\*\*"  # **Speaker Name** (captured)
    r"\s+(\d+:\d{2}(?::\d{2})?)"  # timestamp M:SS or H:MM:SS (captured)
    r"\s*$",  # trailing whitespace / markdown linebreak
)


@dataclass
class SpeakerTurn:
    """A single speaker's turn in the transcript."""

    line_start: int  # 0-indexed line of the ![...] line
    speaker: str
    timestamp_raw: str
    timestamp_seconds: int


@dataclass
class ChunkInfo:
    """Computed boundaries for a single output chunk."""

    index: int
    line_start: int  # 0-indexed, inclusive
    line_end: int  # 0-indexed, inclusive
    time_start: str
    time_end: str
    overlap_prev: int
    overlap_next: int
    turn_count: int


def parse_timestamp(ts: str) -> int:
    """Parse M:SS, MM:SS, or H:MM:SS to total seconds."""
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def format_timestamp(seconds: int) -> str:
    """Total seconds to M:SS or H:MM:SS."""
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def find_speaker_turns(lines: list[str]) -> list[SpeakerTurn]:
    """Scan lines for speaker turn boundaries with timestamps."""
    turns = []
    for i, line in enumerate(lines):
        m = TURN_PATTERN.match(line)
        if m:
            turns.append(
                SpeakerTurn(
                    line_start=i,
                    speaker=m.group(1).strip(),
                    timestamp_raw=m.group(2),
                    timestamp_seconds=parse_timestamp(m.group(2)),
                )
            )
    return turns


def snap_start(line: int, turns: list[SpeakerTurn]) -> int:
    """Snap a line number backward to the nearest turn start at or before it."""
    best = 0
    for t in turns:
        if t.line_start <= line:
            best = t.line_start
        else:
            break
    return best


def snap_end(line: int, turns: list[SpeakerTurn], total_lines: int) -> int:
    """Snap a line number to include the full turn that contains it.

    Finds the turn at or before `line`, then extends to the line before the
    next turn (or EOF).
    """
    turn_idx = 0
    for i, t in enumerate(turns):
        if t.line_start <= line:
            turn_idx = i
        else:
            break
    # End is the line before the next turn, or last line of file
    if turn_idx + 1 < len(turns):
        return turns[turn_idx + 1].line_start - 1
    return total_lines - 1


def turns_in_range(turns: list[SpeakerTurn], start: int, end: int) -> list[SpeakerTurn]:
    """Return turns whose start line falls within [start, end]."""
    return [t for t in turns if start <= t.line_start <= end]


def compute_chunks(
    lines: list[str],
    turns: list[SpeakerTurn],
    chunk_size: int,
    overlap: int,
) -> list[ChunkInfo]:
    """Compute chunk boundaries with sliding window + speaker-turn snapping."""
    total = len(lines)
    stride = chunk_size - overlap
    min_tail = max(overlap * 2, 100)

    # Compute raw window positions, then snap
    chunks: list[ChunkInfo] = []
    pos = 0
    while pos < total:
        raw_start = pos
        raw_end = min(pos + chunk_size - 1, total - 1)

        # Snap boundaries to turn starts
        if chunks:  # chunk 0 always starts at 0 to include header
            snapped_start = snap_start(raw_start, turns) if turns else raw_start
        else:
            snapped_start = 0

        if raw_end >= total - 1:
            snapped_end = total - 1  # last chunk always goes to EOF
        else:
            snapped_end = snap_end(raw_end, turns, total) if turns else raw_end

        chunk_turns = turns_in_range(turns, snapped_start, snapped_end)
        time_start = chunk_turns[0].timestamp_raw if chunk_turns else "?"
        time_end = chunk_turns[-1].timestamp_raw if chunk_turns else "?"

        chunks.append(
            ChunkInfo(
                index=len(chunks),
                line_start=snapped_start,
                line_end=snapped_end,
                time_start=time_start,
                time_end=time_end,
                overlap_prev=0,
                overlap_next=0,
                turn_count=len(chunk_turns),
            )
        )

        # Advance by stride
        next_pos = pos + stride
        if next_pos >= total:
            break
        # Check if remainder would be too small — merge into this chunk
        remaining = total - next_pos
        if remaining < min_tail:
            # Extend current chunk to EOF
            chunks[-1].line_end = total - 1
            chunk_turns = turns_in_range(turns, chunks[-1].line_start, total - 1)
            chunks[-1].time_end = chunk_turns[-1].timestamp_raw if chunk_turns else "?"
            chunks[-1].turn_count = len(chunk_turns)
            break
        pos = next_pos

    # Compute overlap counts between adjacent chunks
    for i in range(len(chunks)):
        if i > 0:
            overlap_start = chunks[i].line_start
            overlap_end = chunks[i - 1].line_end
            chunks[i].overlap_prev = max(0, overlap_end - overlap_start + 1)
        if i < len(chunks) - 1:
            overlap_start = chunks[i + 1].line_start
            overlap_end = chunks[i].line_end
            chunks[i].overlap_next = max(0, overlap_end - overlap_start + 1)

    return chunks


def build_chunk_header(info: ChunkInfo, total_chunks: int, total_lines: int, source: str) -> str:
    """Format the metadata header prepended to each chunk file."""
    return (
        f"--- CHUNK METADATA ---\n"
        f"Chunk: {info.index + 1} / {total_chunks}\n"
        f"Lines: {info.line_start + 1}-{info.line_end + 1} (of {total_lines})\n"
        f"Time: {info.time_start} - {info.time_end}\n"
        f"Turns: {info.turn_count} speaker turns\n"
        f"Overlap: {info.overlap_prev} lines with previous, "
        f"{info.overlap_next} lines with next\n"
        f"Source: {source}\n"
        f"--- END METADATA ---\n\n"
    )


def clean_stale_chunks(output_dir: Path, new_count: int, dry_run: bool) -> int:
    """Remove chunk_NNN.md files with index >= new_count. Returns count removed."""
    removed = 0
    for f in sorted(output_dir.glob("chunk_*.md")):
        try:
            idx = int(f.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if idx >= new_count:
            if not dry_run:
                f.unlink()
            removed += 1
    return removed


def default_output_dir(transcript_path: Path) -> Path:
    """Derive output directory from transcript filename: <name>_chunks/ next to source."""
    return transcript_path.parent / (transcript_path.stem + "_chunks")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chunk a Dockxer transcript into overlapping windows for AI summarization.",
    )
    parser.add_argument("transcript_file", type=Path, help="Path to the .md or .txt transcript file")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        metavar="LINES",
        help="Target chunk size in lines (default: 500)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=100,
        metavar="LINES",
        help="Number of overlapping lines between chunks (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: <transcript_name>_chunks/ next to source)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show chunk plan without writing files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed output including turn boundaries",
    )
    args = parser.parse_args()

    # Validate
    transcript = args.transcript_file.resolve()
    if not transcript.is_file():
        print(f"Error: file not found: {transcript}", file=sys.stderr)
        return 1
    if args.overlap >= args.chunk_size:
        print("Error: overlap must be less than chunk-size", file=sys.stderr)
        return 1

    output_dir = (args.output_dir or default_output_dir(transcript)).resolve()
    stride = args.chunk_size - args.overlap
    overlap_pct = args.overlap / args.chunk_size * 100

    # Read and parse
    content = transcript.read_text(encoding="utf-8")
    lines = content.splitlines()
    turns = find_speaker_turns(lines)

    # Header
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Chunk Transcript")
    print("=" * 50)
    print(f"  Source:  {transcript.name}")
    print(f"  Lines:   {len(lines):,} total")
    print(f"  Turns:   {len(turns)} speaker turns")
    print(f"  Output:  {output_dir}")
    print()
    print(f"  Chunk Size:  {args.chunk_size} lines")
    print(f"  Overlap:     {args.overlap} lines ({overlap_pct:.1f}%)")
    print(f"  Stride:      {stride} lines")

    if not turns:
        print("\n  Warning: no speaker turns detected. Using naive line-based chunking.")

    # Compute chunks
    chunks = compute_chunks(lines, turns, args.chunk_size, args.overlap)

    # Summary table
    print(f"\n  {'Chunk':<8} {'Lines':<16} {'Time Range':<18} {'Turns':>5}  Overlap (prev/next)")
    print(f"  {'-' * 8} {'-' * 16} {'-' * 18} {'-' * 5}  {'-' * 20}")
    for c in chunks:
        chunk_label = f"{c.index + 1}/{len(chunks)}"
        line_range = f"{c.line_start + 1}-{c.line_end + 1}"
        time_range = f"{c.time_start} - {c.time_end}"
        overlap_info = f"{c.overlap_prev} / {c.overlap_next}"
        print(f"  {chunk_label:<8} {line_range:<16} {time_range:<18} {c.turn_count:>5}  {overlap_info}")

    if args.verbose:
        for c in chunks:
            ct = turns_in_range(turns, c.line_start, c.line_end)
            if ct:
                print(f"\n  Chunk {c.index + 1} first turn: [{ct[0].speaker}] @ {ct[0].timestamp_raw}")
                print(f"  Chunk {c.index + 1} last turn:  [{ct[-1].speaker}] @ {ct[-1].timestamp_raw}")

    # Write output
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale chunks
    if output_dir.exists():
        stale = clean_stale_chunks(output_dir, len(chunks), args.dry_run)
        if stale:
            action = "Would remove" if args.dry_run else "Removed"
            print(f"\n  {action} {stale} stale chunk file(s)")

    # Write chunk files
    for c in chunks:
        header = build_chunk_header(c, len(chunks), len(lines), transcript.name)
        chunk_lines = lines[c.line_start : c.line_end + 1]
        chunk_content = header + "\n".join(chunk_lines) + "\n"

        out_path = output_dir / f"chunk_{c.index:03d}.md"
        if args.dry_run:
            if args.verbose:
                print(f"  Would write: {out_path.name} ({len(chunk_lines)} lines)")
        else:
            out_path.write_text(chunk_content, encoding="utf-8")

    # Final summary
    total_chunk_lines = sum(c.line_end - c.line_start + 1 for c in chunks)
    action = "Would write" if args.dry_run else "Wrote"
    print(f"\n  {action} {len(chunks)} chunk files")
    print(f"  Total lines across chunks: {total_chunk_lines:,} "
          f"(~{total_chunk_lines / len(lines):.1f}x original due to overlap)")

    if args.dry_run:
        print(f"\n  Run without --dry-run to apply.\n")
    else:
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
