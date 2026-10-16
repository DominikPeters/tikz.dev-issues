#!/usr/bin/env python3
"""Inventory PGF/TikZ codeexample source without executing TeX.

The automatic hazard tags are review prompts only. Absence of a tag does not
mean an example is safe to cache.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


_BEGIN = re.compile(r"\\begin\s*\{\s*codeexample\s*\}")
_END = re.compile(r"\\end\s*\{\s*codeexample\s*\}")


def _comment_end(text, pos):
    """Return the end of a TeX comment at pos, or None when pos is not one."""
    if text[pos] != "%":
        return None
    slashes = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        slashes += 1
        i -= 1
    if slashes % 2:
        return None
    end = text.find("\n", pos)
    return len(text) if end < 0 else end


def _find_token(pattern, text, start):
    """Find a token outside comments."""
    cursor = start
    while True:
        match = pattern.search(text, cursor)
        if match is None:
            return None
        line_start = text.rfind("\n", 0, match.start()) + 1
        comment_pos = text.find("%", line_start, match.start())
        while comment_pos >= 0 and _comment_end(text, comment_pos) is None:
            comment_pos = text.find("%", comment_pos + 1, match.start())
        if comment_pos >= 0:
            comment_end = _comment_end(text, comment_pos)
            cursor = comment_end
        else:
            return match


def _optional_options(text, pos):
    """Read optional [...] after begin; braces protect embedded brackets."""
    i = pos
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        comment_end = _comment_end(text, i)
        if comment_end is not None:
            i = comment_end
            continue
        break
    if i >= len(text) or text[i] != "[":
        return "", pos, False
    start = i + 1
    i = start
    brace_depth = 0
    bracket_depth = 1
    while i < len(text):
        comment_end = _comment_end(text, i)
        if comment_end is not None:
            i = comment_end
            continue
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
        elif brace_depth == 0:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
                if bracket_depth == 0:
                    return text[start:i], i + 1, True
        i += 1
    # Malformed/unclosed options: preserve the remainder as options and allow
    # the scanner to report no example rather than inventing a body boundary.
    return text[start:], len(text), True


_HAZARDS = (
    ("random_state", re.compile(r"\\(?:pgfmath)?(?:random\w*|setseed)\b|\brand\b", re.I)),
    ("auxiliary_or_reference", re.compile(r"\\(?:label|ref|pageref|autoref|cite|bibcite|addcontentsline)\b", re.I)),
    ("global_definition_or_declaration", re.compile(
        r"\\(?:global|gdef|xdef|edef|def|newcommand|renewcommand|let|pgfdeclare\w*|tikzdeclare\w*|pgfmathdeclare\w*)\b", re.I)),
    ("allocation_or_counter", re.compile(
        r"\\(?:newcount|newdimen|newskip|newbox|newtoks|newif|newread|newwrite|stepcounter|refstepcounter|setcounter|addtocounter)\b", re.I)),
    ("file_io_or_input", re.compile(r"\\(?:openout|write|closeout|read|input|include|InputIfFileExists)\b", re.I)),
    ("library_or_module_load", re.compile(r"\\(?:usetikzlibrary|usepgflibrary|usepgfmodule|RequirePackage|usepackage)\b", re.I)),
    ("remember_picture_or_overlay", re.compile(r"\b(?:remember\s+picture|overlay)\b", re.I)),
    ("named_path_or_picture_state", re.compile(r"\b(?:name\s+path|name\s+prefix|external/force\s+remake)\b", re.I)),
)


def hazard_tags(options, body):
    """Return conservative lexical tags; these are not a purity proof."""
    source = options + "\n" + body
    # Remove comments to avoid tagging examples that only discuss commands.
    clean_lines = []
    for line in source.splitlines():
        i = 0
        while i < len(line):
            comment_end = _comment_end(line, i)
            if comment_end is not None:
                line = line[:i]
                break
            i += 1
        clean_lines.append(line)
    source = "\n".join(clean_lines)
    tags = [tag for tag, pattern in _HAZARDS if pattern.search(source)]
    lowered = options.lower()
    if re.search(r"(?:^|[,\s])code\s+only(?:[,\s]|$)", lowered):
        tags.append("code_only_execution_uncertain")
    if re.search(r"\bexecute\s*=\s*false\b", lowered):
        tags.append("execute_false")
    return sorted(set(tags))


def parse_file(path, relative_to=None):
    """Yield examples from one .tex file, with exact-span and file hashes."""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    rel = Path(path.name) if relative_to is None else path.relative_to(relative_to)
    file_hash = hashlib.sha256(raw).hexdigest()
    ordinal = 0
    cursor = 0
    while True:
        begin = _find_token(_BEGIN, text, cursor)
        if begin is None:
            break
        options, body_start, has_options = _optional_options(text, begin.end())
        end = _find_token(_END, text, body_start)
        if end is None:
            cursor = begin.end()
            continue
        ordinal += 1
        raw_span = text[begin.start():end.end()]
        body = text[body_start:end.start()]
        yield {
            "file": rel.as_posix(),
            "line": text.count("\n", 0, begin.start()) + 1,
            "ordinal": ordinal,
            "start": begin.start(),
            "end": end.end(),
            "begin_end": begin.end(),
            "options_end": body_start if has_options else begin.end(),
            "has_options": has_options,
            "source_sha256": file_hash,
            "source_span_sha256": hashlib.sha256(raw_span.encode("utf-8", errors="surrogateescape")).hexdigest(),
            "options": options,
            "body": body,
            "status": "unreviewed",
            "hazard_tags": hazard_tags(options, body),
        }
        cursor = end.end()


def enumerate_examples(docdir):
    """Yield codeexamples in deterministic path order beneath docdir."""
    root = Path(docdir)
    for path in sorted(root.rglob("*.tex")):
        yield from parse_file(path, relative_to=root)


def cache_id(example):
    """Stable key derived from the file and both source fingerprints."""
    material = (b"render-cache-v1\0" + example["file"].encode("utf-8") + b"\0" +
                example["source_sha256"].encode("ascii") + b"\0" +
                example["source_span_sha256"].encode("ascii"))
    return hashlib.sha256(material).hexdigest()


def apply_cache_tags(docdir, audit_manifest):
    """Insert render-cache options only for exact, reviewed eligible examples.

    Manifest findings are matched by relative file, begin line, complete file
    hash, and exact example-span hash. All offsets are computed from the
    original file, then edits are applied backwards to preserve other bytes.
    """
    root = Path(docdir)
    by_location = {}
    records = audit_manifest.get("examples", [])
    for record_id, record in enumerate(records):
        key = (record.get("file"), record.get("line"))
        by_location.setdefault(key, []).append((record_id, record))

    grouped = {}
    counts = {"tagged": 0, "stale": 0, "ineligible": 0}
    matched_manifest_ids = set()
    for example in enumerate_examples(root):
        candidates = by_location.get((example["file"], example["line"]), [])
        if not candidates:
            continue
        matching = [(record_id, record) for record_id, record in candidates
                    if record.get("source_sha256") == example["source_sha256"] and
                    record.get("source_span_sha256") == example["source_span_sha256"]]
        if not matching:
            if not any(record.get("status") == "eligible" for _, record in candidates):
                counts["ineligible"] += 1
            continue
        for record_id, record in matching:
            if record.get("status") == "eligible":
                matched_manifest_ids.add(record_id)
        record_id, record = matching[0]
        if record.get("status") != "eligible" or "\\begin{tikzpicture}" not in example["body"]:
            counts["ineligible"] += 1
            continue
        if "render cache=" in example["options"]:
            # Existing hand-authored cache settings must not be overwritten.
            counts["ineligible"] += 1
            continue
        insertion = example["options_end"] - 1 if example["has_options"] else example["begin_end"]
        option = ("," if example["has_options"] and example["options"].strip() else "") + "render cache=" + cache_id(example)
        grouped.setdefault(example["file"], []).append((insertion, "[" + option + "]" if not example["has_options"] else option))
        counts["tagged"] += 1

    counts["stale"] = sum(1 for record_id, record in enumerate(records)
                          if record.get("status") == "eligible" and
                          record_id not in matched_manifest_ids)

    for relative, edits in grouped.items():
        path = root / relative
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="surrogateescape")
        for offset, insertion in sorted(edits, reverse=True):
            text = text[:offset] + insertion + text[offset:]
        path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
    return counts


def build_inventory(package, docdir):
    root = Path(docdir)
    return {
        "package": package,
        "docdir": str(root.resolve()),
        "examples": list(enumerate_examples(root)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="package label, for example pgf")
    parser.add_argument("docdir", type=Path, help="prepared manual documentation directory")
    parser.add_argument("--output", "-o", type=Path, required=True, help="JSON inventory destination")
    args = parser.parse_args(argv)
    inventory = build_inventory(args.package, args.docdir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(inventory['examples'])} examples to {args.output}")


if __name__ == "__main__":
    main()
