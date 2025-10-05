"""Utility script to purge transient cache artefacts from the repository.

The script traverses the project tree, deleting common Python caches,
bytecode files, and other build leftovers while keeping virtual
environments and other important directories intact.
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CACHE_DIRECTORIES: tuple[str, ...] = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".hypothesis",
    ".cache",
    ".coverage_cache",
    ".parcel-cache",
    ".svelte-kit",
    ".turbo",
    ".next",
    "build",
    "dist",
    "htmlcov",
)

CACHE_FILE_EXTENSIONS: tuple[str, ...] = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".cache",
)

CACHE_FILE_NAMES: tuple[str, ...] = (
    ".coverage",
    "coverage.xml",
)

SKIP_DIRECTORY_NAMES: tuple[str, ...] = (
    ".venv",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
)


@dataclass
class RemovalStats:
    """Simple bookkeeping for cache removal operations."""

    directories: int = 0
    files: int = 0
    bytes: int = 0


def iter_cache_directories(root: Path) -> Iterable[Path]:
    """Yield cache directories and files under ``root`` that may be removed."""
    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)

        if current_dir.name in SKIP_DIRECTORY_NAMES:
            dirnames[:] = []
            continue

        for dirname in list(dirnames):
            if dirname in SKIP_DIRECTORY_NAMES:
                dirnames.remove(dirname)
                continue
            if dirname in CACHE_DIRECTORIES:
                target_dir = current_dir / dirname
                dirnames.remove(dirname)
                yield target_dir

        for filename in filenames:
            file_path = current_dir / filename
            if filename in CACHE_FILE_NAMES or file_path.suffix in CACHE_FILE_EXTENSIONS:
                yield file_path


def _calculate_size(path: Path) -> int:
    """Calculate the size of ``path`` in bytes, ignoring inaccessible entries."""
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            total = 0
            for entry in path.rglob("*"):
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except OSError:
                    continue
            return total
        return 0
    except OSError:
        return 0


def _remove_path(path: Path, *, dry_run: bool, verbose: bool) -> tuple[int, int, int]:
    """Remove ``path`` and return (dir_count, file_count, size_bytes)."""
    size = _calculate_size(path)
    if verbose:
        action = "Would remove" if dry_run else "Removing"
        print(f"{action}: {path}")

    if dry_run:
        return (1 if path.is_dir() else 0, 1 if path.is_file() else 0, size)

    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
            return (1, 0, size)
        if path.exists():
            path.unlink()
            return (0, 1, size)
    except OSError as exc:
        if verbose:
            print(f"Failed to remove {path}: {exc}")
    return (0, 0, 0)


def clear_cache(root: Path, *, dry_run: bool = False, verbose: bool = False) -> RemovalStats:
    """Delete cached content below ``root`` and return removal statistics."""
    stats = RemovalStats()
    for target in iter_cache_directories(root):
        dirs, files, size = _remove_path(target, dry_run=dry_run, verbose=verbose)
        stats.directories += dirs
        stats.files += files
        stats.bytes += size
    return stats


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Remove Python cache directories and bytecode files from the "
            "project while keeping virtual environments intact."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Base directory to clean. Defaults to the repository root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each path as it is considered for removal.",
    )
    return parser.parse_args()


def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} {units[-1]}"


def main() -> None:
    """Entrypoint for the cache clearing script."""
    args = parse_args()
    stats = clear_cache(args.path.resolve(), dry_run=args.dry_run, verbose=args.verbose)

    action = "Would remove" if args.dry_run else "Removed"
    summary = (
        f"{action} {stats.directories} directories and {stats.files} files "
        f"({_format_size(stats.bytes)})"
    )
    print(summary)


if __name__ == "__main__":
    main()
