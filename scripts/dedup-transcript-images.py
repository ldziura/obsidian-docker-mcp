#!/usr/bin/env python3
"""Deduplicate and resize profile images in Dockxer-converted meeting transcripts.

The Dockxer Obsidian plugin converts Teams .docx transcripts to .md but stores
every speaker profile picture as a separate PNG file. This script identifies
duplicate images by content hash, keeps one copy of each unique image in a
shared folder, rewrites the markdown references, deletes the duplicates, and
optionally resizes images by setting their alt text to a pixel width.
"""

import argparse
import hashlib
import re
import shutil
import sys
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Import sibling script for resize functionality
sys.path.insert(0, str(Path(__file__).parent))
from resize_transcript_images import resize_images

IMAGE_PATTERN = re.compile(
    r"!\[([^\]]*)\]"  # ![alt text]
    r"\("  # (
    r"<([^>]+\.(?:png|jpe?g|gif|webp|bmp|svg))>"  # <url-encoded vault-relative path>
    r"\)",  # )
    re.IGNORECASE,
)


@dataclass
class ImageRef:
    """A single image reference found in the markdown."""

    alt_text: str
    url_encoded_path: str
    decoded_path: str
    absolute_path: Path
    full_match: str


@dataclass
class Stats:
    """Deduplication run statistics."""

    total_refs: int = 0
    unique_images: int = 0
    duplicates_removed: int = 0
    bytes_freed: int = 0
    missing_files: int = 0
    errors: list[str] = field(default_factory=list)


def find_vault_root(start: Path) -> Path | None:
    """Walk up from start looking for a directory containing .obsidian/."""
    current = start if start.is_dir() else start.parent
    for _ in range(20):  # safety limit
        if (current / ".obsidian").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def parse_image_refs(content: str, vault_root: Path) -> list[ImageRef]:
    """Extract all image references from markdown content."""
    refs = []
    for match in IMAGE_PATTERN.finditer(content):
        alt_text = match.group(1)
        url_path = match.group(2)
        decoded = urllib.parse.unquote(url_path)
        absolute = vault_root / decoded
        refs.append(
            ImageRef(
                alt_text=alt_text,
                url_encoded_path=url_path,
                decoded_path=decoded,
                absolute_path=absolute,
                full_match=match.group(0),
            )
        )
    return refs


def hash_file(filepath: Path) -> str:
    """Return SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def group_by_hash(refs: list[ImageRef], verbose: bool = False) -> dict[str, list[ImageRef]]:
    """Group image references by file content hash. Skips missing files."""
    groups: dict[str, list[ImageRef]] = defaultdict(list)
    missing = 0
    for i, ref in enumerate(refs):
        if not ref.absolute_path.is_file():
            missing += 1
            if verbose:
                print(f"  Warning: missing file: {ref.decoded_path}")
            continue
        file_hash = hash_file(ref.absolute_path)
        groups[file_hash].append(ref)
        if verbose and (i + 1) % 100 == 0:
            print(f"  Hashed {i + 1}/{len(refs)}...")
    if missing:
        print(f"  Skipped {missing} missing file(s)")
    return dict(groups)


def build_path_map(
    groups: dict[str, list[ImageRef]],
    avatar_dir: Path,
    vault_root: Path,
) -> dict[str, str]:
    """Build old→new URL-encoded path mapping for each image reference.

    Returns {old_url_encoded_path: new_url_encoded_path}.
    """
    path_map: dict[str, str] = {}
    for file_hash, refs in groups.items():
        ext = refs[0].absolute_path.suffix.lower()
        new_filename = f"avatar_{file_hash[:12]}{ext}"
        new_vault_relative = avatar_dir.as_posix() + "/" + new_filename
        # URL-encode: only spaces need encoding based on observed Dockxer output
        new_encoded = urllib.parse.quote(new_vault_relative, safe="/'!()&-_.")
        for ref in refs:
            path_map[ref.url_encoded_path] = new_encoded
    return path_map


def copy_unique_images(
    groups: dict[str, list[ImageRef]],
    avatar_dir_abs: Path,
    dry_run: bool = False,
) -> list[Path]:
    """Copy one representative image per hash group to the avatar directory."""
    created = []
    for file_hash, refs in groups.items():
        ext = refs[0].absolute_path.suffix.lower()
        new_filename = f"avatar_{file_hash[:12]}{ext}"
        dest = avatar_dir_abs / new_filename
        if dest.exists():
            continue
        if dry_run:
            print(f"  Would copy: {refs[0].decoded_path} -> {dest.name}")
        else:
            shutil.copy2(refs[0].absolute_path, dest)
        created.append(dest)
    return created


def rewrite_markdown(content: str, path_map: dict[str, str]) -> str:
    """Replace old image paths with new deduplicated paths in markdown."""
    for old_path, new_path in path_map.items():
        content = content.replace(f"<{old_path}>", f"<{new_path}>")
    return content


def delete_originals(
    groups: dict[str, list[ImageRef]],
    dry_run: bool = False,
) -> tuple[int, int]:
    """Delete all original duplicate image files.

    Returns (count_deleted, bytes_freed).
    """
    count = 0
    freed = 0
    # Collect all unique absolute paths to delete (avoid double-counting)
    seen: set[Path] = set()
    for refs in groups.values():
        for ref in refs:
            if ref.absolute_path in seen:
                continue
            seen.add(ref.absolute_path)
            if not ref.absolute_path.is_file():
                continue
            size = ref.absolute_path.stat().st_size
            if dry_run:
                pass  # just count
            else:
                ref.absolute_path.unlink()
            count += 1
            freed += size
    return count, freed


def print_table(groups: dict[str, list[ImageRef]], avatar_dir: str) -> None:
    """Print a summary table of unique images."""
    print(f"\n  {'Hash':<16} {'Size':>8}  {'Count':>5}  Destination")
    print(f"  {'-' * 16} {'-' * 8}  {'-' * 5}  {'-' * 40}")
    for file_hash, refs in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        size = refs[0].absolute_path.stat().st_size if refs[0].absolute_path.is_file() else 0
        ext = refs[0].absolute_path.suffix.lower()
        dest = f"{avatar_dir}/avatar_{file_hash[:12]}{ext}"
        print(f"  {file_hash[:16]:<16} {size:>8,}  {len(refs):>5}  {dest}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deduplicate profile images in Dockxer-converted meeting transcripts.",
    )
    parser.add_argument("markdown_file", type=Path, help="Path to the .md transcript file")
    parser.add_argument(
        "--avatar-dir",
        default="assets/transcript-avatars",
        help="Vault-relative path for deduplicated images (default: assets/transcript-avatars)",
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=None,
        help="Vault root directory (auto-detected if not specified)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--resize",
        type=int,
        default=40,
        metavar="PX",
        help="Resize images by setting alt text to this pixel width (default: 40)",
    )
    parser.add_argument(
        "--no-resize",
        action="store_true",
        help="Skip image resizing (only deduplicate)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed progress output",
    )
    args = parser.parse_args()

    md_path = args.markdown_file.resolve()
    if not md_path.is_file():
        print(f"Error: file not found: {md_path}", file=sys.stderr)
        return 1

    # Detect vault root
    vault_root = args.vault_root.resolve() if args.vault_root else find_vault_root(md_path)
    if vault_root is None:
        print(
            "Error: could not detect vault root (.obsidian/ not found). Use --vault-root.",
            file=sys.stderr,
        )
        return 1

    avatar_dir_rel = Path(args.avatar_dir)
    avatar_dir_abs = vault_root / avatar_dir_rel

    # Header
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Dedup Transcript Images")
    print("=" * 50)
    print(f"  File:  {md_path.relative_to(vault_root)}")
    print(f"  Vault: {vault_root}")
    print(f"  Dest:  {avatar_dir_rel}")
    print()

    # Parse markdown
    content = md_path.read_text(encoding="utf-8")
    refs = parse_image_refs(content, vault_root)
    print(f"  Image references found: {len(refs)}")

    if not refs:
        print("  Nothing to deduplicate.")
        return 0

    # Check for already-deduplicated references
    avatar_prefix = avatar_dir_rel.as_posix()
    new_refs = [r for r in refs if not r.decoded_path.startswith(avatar_prefix)]
    if len(new_refs) < len(refs):
        skipped = len(refs) - len(new_refs)
        print(f"  Skipping {skipped} already-deduplicated reference(s)")
        refs = new_refs

    if not refs:
        print("  All references already deduplicated.")
        return 0

    # Hash and group
    print("  Hashing images...")
    groups = group_by_hash(refs, verbose=args.verbose)
    total_referenced = sum(len(g) for g in groups.values())
    print(f"  Unique images: {len(groups)}")
    print(f"  Total referenced (valid): {total_referenced}")
    print(f"  Duplicates: {total_referenced - len(groups)}")

    if len(groups) == total_referenced:
        print("\n  No duplicates found. Nothing to do.")
        return 0

    # Show summary table
    print_table(groups, args.avatar_dir)

    # Create avatar directory
    if not args.dry_run:
        avatar_dir_abs.mkdir(parents=True, exist_ok=True)
    else:
        print(f"  Would create directory: {avatar_dir_rel}")

    # Copy unique images
    print("  Copying unique images...")
    copy_unique_images(groups, avatar_dir_abs, dry_run=args.dry_run)

    # Build path map and rewrite markdown
    path_map = build_path_map(groups, avatar_dir_rel, vault_root)
    new_content = rewrite_markdown(content, path_map)

    # Resize images (set alt text to pixel width)
    resize_count = 0
    if not args.no_resize:
        new_content, resize_count = resize_images(new_content, args.resize)

    if args.dry_run:
        changed = sum(1 for old, new in path_map.items() if old != new)
        print(f"  Would rewrite {changed} image reference(s) in markdown")
        if resize_count:
            print(f"  Would resize {resize_count} image(s) to {args.resize}px")
    else:
        md_path.write_text(new_content, encoding="utf-8")
        print("  Markdown references rewritten")
        if resize_count:
            print(f"  Resized {resize_count} image(s) to {args.resize}px")

    # Delete originals
    print("  Cleaning up original files...")
    count_deleted, bytes_freed = delete_originals(groups, dry_run=args.dry_run)

    # Summary
    action = "Would remove" if args.dry_run else "Removed"
    print(f"\n  Summary:")
    print(f"    Images kept:      {len(groups)} (in {args.avatar_dir}/)")
    print(f"    {action}: {count_deleted} file(s)")
    print(f"    Space freed:      {bytes_freed / 1024 / 1024:.2f} MB")

    if args.dry_run:
        print(f"\n  Run without --dry-run to apply changes.\n")
    else:
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
