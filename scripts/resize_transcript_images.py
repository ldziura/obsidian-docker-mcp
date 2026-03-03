#!/usr/bin/env python3
"""Resize images in Obsidian markdown files by setting the alt text to a pixel width.

Obsidian renders ![40](<path.png>) as a 40px-wide image. This script replaces
the alt text of all image references in a markdown file with a size value,
making large profile pictures (from Dockxer transcripts, etc.) display inline
at a readable size.
"""

import argparse
import re
import sys
from pathlib import Path

IMAGE_PATTERN = re.compile(
    r"(!\[)"           # ![ prefix
    r"([^\]]*)"        # alt text (captured for replacement check)
    r"(\]\("           # ](
    r"<[^>]+\.(?:png|jpe?g|gif|webp|bmp|svg)>"  # <path.ext>
    r"\))",            # )
    re.IGNORECASE,
)


def resize_images(content: str, size: int) -> tuple[str, int]:
    """Replace alt text in image references with a pixel size.

    Returns (new_content, count_of_replacements).
    """
    count = 0
    size_str = str(size)

    def replace_alt(match: re.Match) -> str:
        nonlocal count
        prefix = match.group(1)   # ![
        alt = match.group(2)      # current alt text
        suffix = match.group(3)   # ](<path>)
        if alt == size_str:
            return match.group(0)  # already correct size, skip
        count += 1
        return f"{prefix}{size_str}{suffix}"

    new_content = IMAGE_PATTERN.sub(replace_alt, content)
    return new_content, count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resize images in Obsidian markdown by setting alt text to a pixel width.",
    )
    parser.add_argument("markdown_file", type=Path, help="Path to the .md file")
    parser.add_argument(
        "--size",
        type=int,
        default=40,
        help="Image width in pixels (default: 40)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    md_path = args.markdown_file.resolve()
    if not md_path.is_file():
        print(f"Error: file not found: {md_path}", file=sys.stderr)
        return 1

    content = md_path.read_text(encoding="utf-8")
    new_content, count = resize_images(content, args.size)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Resize Transcript Images")
    print(f"  File: {md_path}")
    print(f"  Size: {args.size}px")

    if count == 0:
        print(f"  No changes needed (all images already at {args.size}px)")
        return 0

    action = "Would resize" if args.dry_run else "Resized"
    print(f"  {action} {count} image reference(s)")

    if not args.dry_run:
        md_path.write_text(new_content, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
