"""Tool implementations exposed to the coder and reviewer agents.

Each tool is a pure function operating on the filesystem under a
supplied ``workdir``. The module also exposes JSON schemas compatible
with the Anthropic Messages API ``tools`` parameter and a dispatcher
that maps a tool name to its Python implementation.

The split between ``READ_TOOLS`` and ``WRITE_TOOLS`` is what enforces
the reviewer being read-only.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional


# --- helpers ---------------------------------------------------------------


def _resolve(workdir: Path, path: str) -> Path:
    """Resolve ``path`` against ``workdir`` and refuse escapes.

    Both ``workdir`` and the resolved target are normalised. If the
    resolved target is not under ``workdir`` we raise ``ValueError`` —
    this is a soft sandbox against path traversal in model-generated
    tool calls.
    """
    workdir = workdir.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workdir / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workdir)
    except ValueError as exc:  # not a subpath
        raise ValueError(
            f"path {path!r} escapes workdir {workdir}"
        ) from exc
    return resolved


# --- tool implementations --------------------------------------------------


def read_file(workdir: Path, path: str) -> str:
    target = _resolve(workdir, path)
    if not target.exists():
        raise FileNotFoundError(f"{path}: no such file")
    if target.is_dir():
        raise IsADirectoryError(f"{path}: is a directory")
    return target.read_text(encoding="utf-8")


def write_file(workdir: Path, path: str, content: str) -> str:
    target = _resolve(workdir, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


def edit_file(
    workdir: Path,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    if old_string == new_string:
        raise ValueError("old_string and new_string are identical")
    target = _resolve(workdir, path)
    text = target.read_text(encoding="utf-8")
    if replace_all:
        if old_string not in text:
            raise ValueError(f"{path}: old_string not found")
        count = text.count(old_string)
        text = text.replace(old_string, new_string)
        target.write_text(text, encoding="utf-8")
        return f"replaced {count} occurrences in {path}"
    count = text.count(old_string)
    if count == 0:
        raise ValueError(f"{path}: old_string not found")
    if count > 1:
        raise ValueError(
            f"{path}: old_string matches {count} times; "
            "pass replace_all=True or widen the match"
        )
    text = text.replace(old_string, new_string, 1)
    target.write_text(text, encoding="utf-8")
    return f"replaced 1 occurrence in {path}"


def grep(
    workdir: Path,
    pattern: str,
    path: Optional[str] = None,
    glob: Optional[str] = None,
    max_results: int = 200,
) -> str:
    """Recursive content search. Returns ``path:line:text`` lines."""
    root = _resolve(workdir, path) if path else workdir.resolve()
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
    matches: List[str] = []
    for file_path in _iter_files(root, glob):
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if regex.search(line):
                        rel = file_path.relative_to(workdir.resolve())
                        matches.append(
                            f"{rel}:{lineno}:{line.rstrip()}"
                        )
                        if len(matches) >= max_results:
                            matches.append(
                                f"(truncated at {max_results} matches)"
                            )
                            return "\n".join(matches)
        except OSError:
            continue
    return "\n".join(matches) if matches else "(no matches)"


def glob_tool(
    workdir: Path,
    pattern: str,
    path: Optional[str] = None,
    max_results: int = 500,
) -> str:
    root = _resolve(workdir, path) if path else workdir.resolve()
    results: List[str] = []
    for file_path in _iter_files(root, None):
        rel = file_path.relative_to(workdir.resolve())
        if fnmatch.fnmatch(str(rel), pattern) or fnmatch.fnmatch(
            file_path.name, pattern
        ):
            results.append(str(rel))
            if len(results) >= max_results:
                results.append(f"(truncated at {max_results} files)")
                break
    results.sort()
    return "\n".join(results) if results else "(no matches)"


# --- walker ----------------------------------------------------------------


_IGNORE_DIRS = {".git", ".harness", "__pycache__", ".venv", "node_modules"}


def _iter_files(root: Path, glob: Optional[str]):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored directories in-place for speed
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for name in filenames:
            if glob and not fnmatch.fnmatch(name, glob):
                continue
            yield Path(dirpath) / name


# --- schemas ---------------------------------------------------------------

READ_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the full contents of a file, relative to the project root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": (
            "Search file contents with a Python regex. Returns matching "
            "lines as 'path:line:text'. Optional 'path' narrows the scan "
            "root; optional 'glob' filters file names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": (
            "List files whose path matches a glob pattern like '**/*.py'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
]

WRITE_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "write_file",
        "description": (
            "Overwrite the contents of a file (or create it). Parent "
            "directories are created as needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file. 'old_string' must match "
            "exactly once unless replace_all=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
]


# --- dispatcher ------------------------------------------------------------


@dataclass(frozen=True)
class Toolset:
    """A named bundle of tool schemas and handlers bound to a workdir."""

    schemas: List[Dict[str, Any]]
    handlers: Dict[str, Callable[..., str]]

    def call(self, name: str, arguments: Mapping[str, Any]) -> str:
        handler = self.handlers.get(name)
        if handler is None:
            raise KeyError(f"unknown tool: {name}")
        return handler(**arguments)


def reader_toolset(workdir: Path) -> Toolset:
    handlers: Dict[str, Callable[..., str]] = {
        "read_file": lambda path: read_file(workdir, path),
        "grep": lambda pattern, path=None, glob=None: grep(
            workdir, pattern, path, glob
        ),
        "glob": lambda pattern, path=None: glob_tool(workdir, pattern, path),
    }
    return Toolset(schemas=list(READ_SCHEMAS), handlers=handlers)


def writer_toolset(workdir: Path) -> Toolset:
    read = reader_toolset(workdir)
    handlers: Dict[str, Callable[..., str]] = dict(read.handlers)
    handlers["write_file"] = lambda path, content: write_file(
        workdir, path, content
    )
    handlers["edit_file"] = lambda path, old_string, new_string, replace_all=False: edit_file(
        workdir, path, old_string, new_string, replace_all
    )
    return Toolset(
        schemas=list(READ_SCHEMAS) + list(WRITE_SCHEMAS),
        handlers=handlers,
    )


__all__ = [
    "Toolset",
    "reader_toolset",
    "writer_toolset",
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "glob_tool",
    "READ_SCHEMAS",
    "WRITE_SCHEMAS",
]
