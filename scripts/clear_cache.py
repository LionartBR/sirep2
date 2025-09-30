#!/usr/bin/env python3
"""Utility to remove Python cache artifacts from the project tree."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable, Sequence

CACHE_DIR_NAMES: Sequence[str] = (
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
)
CACHE_FILE_PATTERNS: Sequence[str] = (
    "*.py[cod]",
    "*.pyo",
    "*.pyd",
    ".coverage",
    ".coverage.*",
)


def gather_cache_directories(root: Path) -> list[Path]:
    """Collect cache directories within ``root``."""
    directories: set[Path] = set()
    for name in CACHE_DIR_NAMES:
        for path in root.rglob(name):
            if path.is_dir():
                directories.add(path)
    return sorted(directories, key=lambda path: (-len(path.parts), str(path)))


def gather_cache_files(root: Path) -> list[Path]:
    """Collect cache files within ``root``."""
    files: set[Path] = set()
    for pattern in CACHE_FILE_PATTERNS:
        for path in root.rglob(pattern):
            if path.is_file():
                files.add(path)
    return sorted(files)


def remove_paths(paths: Iterable[Path], dry_run: bool) -> None:
    for path in paths:
        if dry_run:
            print(f"Would remove: {path}")
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            print(f"Removed directory: {path}")
        elif path.exists():
            path.unlink(missing_ok=True)
            print(f"Removed file: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove Python cache artifacts from the project tree.")
    parser.add_argument(
        "path",
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Project root (defaults to the repository root).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files and directories that would be removed without deleting them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.path.resolve()

    if not root.exists():
        raise SystemExit(f"Provided path does not exist: {root}")

    cache_dirs = gather_cache_directories(root)
    cache_files = gather_cache_files(root)

    if not cache_dirs and not cache_files:
        message = "No cache artifacts found." if not args.dry_run else "No cache artifacts would be removed."
        print(message)
        return

    remove_paths(cache_dirs, args.dry_run)
    remove_paths(cache_files, args.dry_run)


if __name__ == "__main__":
    main()
