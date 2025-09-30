"""Utility script to remove cached artifacts from the repository.

The script walks through the project tree and deletes common Python cache
folders and bytecode files while keeping the virtual environment intact.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Iterable


CACHE_DIRECTORIES: tuple[str, ...] = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".hypothesis",
)

CACHE_FILE_EXTENSIONS: tuple[str, ...] = (".pyc", ".pyo", ".pyd")

VENV_DIRECTORY_NAMES: tuple[str, ...] = (".venv",)


def should_skip_directory(path: Path) -> bool:
    """Return True when the directory should be skipped during traversal."""
    return path.name in VENV_DIRECTORY_NAMES


def remove_directory(path: Path) -> None:
    """Remove the provided directory recursively if it exists."""
    shutil.rmtree(path)


def remove_file(path: Path) -> None:
    """Remove the provided file if it exists."""
    path.unlink()


def iter_cache_directories(root: Path) -> Iterable[Path]:
    """Yield cache directories under ``root`` that can be safely removed."""
    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)
        if should_skip_directory(current_dir):
            dirnames[:] = []
            continue

        for dirname in list(dirnames):
            if dirname in CACHE_DIRECTORIES:
                target_dir = current_dir / dirname
                dirnames.remove(dirname)
                yield target_dir

        for filename in filenames:
            if Path(filename).suffix in CACHE_FILE_EXTENSIONS:
                yield current_dir / filename


def clear_cache(root: Path) -> None:
    """Delete cached directories and files underneath ``root``."""
    for target in iter_cache_directories(root):
        if target.is_dir():
            remove_directory(target)
        elif target.is_file():
            remove_file(target)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Remove Python cache directories and bytecode files from the "
            "project while keeping the virtual environment intact."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="Base directory to clean. Defaults to the repository root.",
    )
    return parser.parse_args()


def main() -> None:
    """Entrypoint for the cache clearing script."""
    args = parse_args()
    clear_cache(args.path.resolve())


if __name__ == "__main__":
    main()
