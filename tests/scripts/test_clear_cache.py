"""Tests for the cache clearing utility script."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.clear_cache import iter_cache_directories


def test_iter_cache_directories_in_repo_under_virtualenv(tmp_path: Path) -> None:
    """Ensure caches are detected when the project root is inside a virtualenv."""
    root = tmp_path / ".venv" / "project"
    cache_dir = root / "__pycache__"
    cache_dir.mkdir(parents=True)
    bytecode_file = root / "module.pyc"
    bytecode_file.write_text("")

    targets = list(iter_cache_directories(root))

    assert cache_dir in targets
    assert bytecode_file in targets


def test_iter_cache_directories_skip_nested_virtualenv(tmp_path: Path) -> None:
    """Verify that nested virtual environment directories are not traversed."""
    root = tmp_path / "project"
    cache_dir = root / "__pycache__"
    cache_dir.mkdir(parents=True)
    nested_venv_cache = root / ".venv" / "__pycache__"
    nested_venv_cache.mkdir(parents=True)

    targets = list(iter_cache_directories(root))

    assert cache_dir in targets
    assert not any(target.is_relative_to(root / ".venv") for target in targets)
