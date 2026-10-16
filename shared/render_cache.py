#!/usr/bin/env python3
"""Cache original illustration pages between LuaLaTeX passes of one build."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import Sequence


_KEY = re.compile(r"^[a-f0-9]{64}-[0-9]+$")
_PENDING_SUFFIX = ".render-cache-pending.jsonl"
_CACHE_SUFFIX = ".render-cache"


@dataclass(frozen=True)
class PendingPage:
    key: str
    page: int
    pgf_ids: int


class RenderCacheError(RuntimeError):
    """A pending cache record or source PDF cannot be used safely."""


def _job_file(job: Path, extension: str) -> Path:
    return Path(f"{job}{extension}")


def _cache_dir(job: Path) -> Path:
    return job.parent / f"{job.name}{_CACHE_SUFFIX}"


def _pending_file(job: Path) -> Path:
    return _job_file(job, _PENDING_SUFFIX)


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _parse_pending(job: Path) -> list[PendingPage]:
    pending_path = _pending_file(job)
    if not pending_path.exists():
        return []

    records: list[PendingPage] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        pending_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            raise RenderCacheError(f"{pending_path}:{line_number}: blank record")
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RenderCacheError(
                f"{pending_path}:{line_number}: malformed JSON record: {exc}"
            ) from exc
        if not isinstance(value, dict) or set(value) != {"key", "page", "pgf_ids"}:
            raise RenderCacheError(
                f"{pending_path}:{line_number}: expected exactly key, page, and pgf_ids"
            )

        key = value["key"]
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise RenderCacheError(
                f"{pending_path}:{line_number}: invalid cache key {key!r}"
            )
        if key in seen:
            raise RenderCacheError(
                f"{pending_path}:{line_number}: duplicate cache key {key!r}"
            )
        seen.add(key)

        page = value["page"]
        pgf_ids = value["pgf_ids"]
        if type(page) is not int or page < 1:
            raise RenderCacheError(
                f"{pending_path}:{line_number}: page must be a positive integer"
            )
        if type(pgf_ids) is not int or pgf_ids < 1:
            raise RenderCacheError(
                f"{pending_path}:{line_number}: pgf_ids must be a positive integer"
            )
        records.append(PendingPage(key, page, pgf_ids))
    return records


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def extract_pending_pages(job: Path) -> int:
    """Extract original PDF pages named in the previous pass's JSONL manifest.

    job is the output job path without an extension (for example build/main).
    Pages and their minimal TeX metadata are written under build/main.render-cache.
    The manifest is removed only after every record has been safely written.
    """
    job = Path(job)
    cache_dir = _cache_dir(job)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pending_path = _pending_file(job)
    records = _parse_pending(job)
    if not records:
        if pending_path.exists():
            pending_path.unlink()
        return 0

    pdf_path = _job_file(job, ".pdf")
    if not pdf_path.is_file():
        raise RenderCacheError(
            f"{pending_path} contains pending pages, but source PDF {pdf_path} is missing"
        )
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import _base as pypdf_base
    except ImportError as exc:
        raise RenderCacheError("pypdf is required to extract render-cache pages") from exc

    pypdf_base.FLOAT_WRITE_PRECISION = 16
    reader = PdfReader(str(pdf_path), strict=True)
    for record in records:
        if record.page > len(reader.pages):
            raise RenderCacheError(
                f"{pdf_path}: page {record.page} is outside the PDF's "
                f"1..{len(reader.pages)} page range"
            )
        writer = PdfWriter()
        writer.add_page(reader.pages[record.page - 1])
        buffer = BytesIO()
        writer.write(buffer)
        _atomic_write(cache_dir / f"{record.key}.pdf", buffer.getvalue())
        tex = rf"\expandafter\def\csname TDC@pgfids\endcsname{{{record.pgf_ids}}}".encode("ascii")
        _atomic_write(cache_dir / f"{record.key}.tex", tex)

    pending_path.unlink()
    return len(records)


def _job_from_args(arguments: Sequence[str], cwd: Path | None = None) -> Path:
    cwd = Path.cwd() if cwd is None else Path(cwd)
    jobname: str | None = None
    output_directory: str | None = None
    source: str | None = None
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg == "-jobname":
            if index + 1 >= len(arguments):
                raise RenderCacheError("-jobname requires a value")
            jobname = arguments[index + 1]
            index += 2
            continue
        if arg in ("-output-directory", "--output-directory"):
            if index + 1 >= len(arguments):
                raise RenderCacheError(f"{arg} requires a value")
            output_directory = arguments[index + 1]
            index += 2
            continue
        if arg.startswith("-jobname="):
            jobname = arg.partition("=")[2]
        elif arg.startswith(("-output-directory=", "--output-directory=")):
            output_directory = arg.partition("=")[2]
        elif not arg.startswith("-") and arg.lower().endswith(".tex"):
            source = arg
        elif not arg.startswith("-") and source is None:
            source = arg
        index += 1

    output_dir = Path(output_directory) if output_directory else Path()
    output_dir = output_dir if output_dir.is_absolute() else cwd / output_dir
    if jobname:
        path = Path(jobname)
        if path.is_absolute():
            return path
        return output_dir / path
    if source is None:
        raise RenderCacheError("cannot derive jobname: pass -jobname or a source file")
    path = Path(source)
    if path.suffix.lower() == ".tex":
        path = path.with_suffix("")
    elif path.suffix:
        raise RenderCacheError(f"cannot derive jobname from input {source!r}")
    return output_dir / path.name


def main(argv: Sequence[str] | None = None) -> int:
    engine_args = list(sys.argv[1:] if argv is None else argv)
    if engine_args and engine_args[0] == "--":
        engine_args.pop(0)
    if not engine_args:
        print("usage: render_cache.py [lualatex arguments]", file=sys.stderr)
        return 2
    try:
        job = _job_from_args(engine_args)
        extract_pending_pages(job)
    except (RenderCacheError, OSError, UnicodeError) as exc:
        print(f"render_cache: {exc}", file=sys.stderr)
        return 2
    return subprocess.call(["lualatex", *engine_args])


if __name__ == "__main__":
    raise SystemExit(main())
