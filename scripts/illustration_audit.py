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
import subprocess
from collections import Counter


_BEGIN = re.compile(r"\\begin\s*\{\s*codeexample\s*\}")
_END = re.compile(r"\\end\s*\{\s*codeexample\s*\}")
_PICTURE = re.compile(r"\\(begin|end)\s*\{\s*tikzpicture\s*\}")


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
    # The starburst shape reseeds PGF's shared generator to its configured
    # seed, then uses \pgfmathrnd; that routine globally advances the shared
    # RNG state. Skipping such a shape can therefore change later unseeded
    # rand/rnd output even though the burst's own points are deterministic.
    ("random_state", re.compile(r"\\(?:pgfmath)?(?:random\w*|setseed|declarerandomlist)\b|\b(?:rand|rnd|random\s+steps|random\s+starburst|starburst)\b", re.I)),
    ("auxiliary_or_reference", re.compile(r"\\(?:label|ref|pageref|autoref|cite|bibcite|addcontentsline)\b", re.I)),
    ("global_definition_or_declaration", re.compile(
        r"\\(?:global|gdef|xdef|edef|def|newcommand|renewcommand|let|pgfdeclare\w*|tikzdeclare\w*|pgfmathdeclare\w*)\b", re.I)),
    ("allocation_or_counter", re.compile(
        r"\\(?:newcount|newdimen|newskip|newbox|newtoks|newif|newread|newwrite|stepcounter|refstepcounter|setcounter|addtocounter)\b", re.I)),
    ("file_io_or_input", re.compile(r"\\(?:openout|openin|write|closeout|closein|read|input|include|InputIfFileExists)(?![A-Za-z@])", re.I)),
    ("library_or_module_load", re.compile(r"\\(?:usetikzlibrary|usepgflibrary|usepgfmodule|RequirePackage|usepackage)\b", re.I)),
    ("remember_picture_or_overlay", re.compile(r"\b(?:remember\s+picture|overlay)\b", re.I)),
    ("named_path_or_picture_state", re.compile(r"\b(?:name\s+path|name\s+prefix|external/force\s+remake)\b", re.I)),
    ("external_plot_or_data", re.compile(
        r"\\(?:addplot\w*\s*(?:\[[\s\S]*?\])?\s*(?:file|gnuplot|graphics|shell)\b|"
        r"pgfplotstableread\b|pgfplotstablewrite\b)|"
        r"\b(?:contour\s+(?:lua|gnuplot)|shell\s+escape|external/|name\s+path\s+global)\b|"
        r"\bshell\b|\bplot\s*(?:\[[^\]]*\]\s*)?function\s*\{|"
        r"\btable\s*(?:\[[^\]]*\]\s*)?\{\s*[^{}\s]+\.(?:dat|csv|txt|tsv)\s*\}", re.I)),
    ("lua_or_externalization", re.compile(
        r"\\(?:directlua|latelua|luaexec|tikzexternal\w*|tikzsetnextfilename|tikzpicturedependsonfile)\b", re.I)),
    ("external_image", re.compile(r"\\(?:includegraphics|pgfimage|pdfximage|saveimageresource)(?![A-Za-z@])", re.I)),
    ("persistent_layer_state", re.compile(r"\\pgfsetlayers(?![A-Za-z@])", re.I)),
)


def strip_comments(source):
    """Remove TeX comments without treating escaped percent signs as comments."""
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
    return "\n".join(clean_lines)


def hazard_tags(options, body):
    """Return conservative lexical tags; these are not a purity proof."""
    source = strip_comments(options + "\n" + body)
    tags = [tag for tag, pattern in _HAZARDS if pattern.search(source)]
    lowered = options.lower()
    if re.search(r"(?:^|[,\s])code\s+only(?:[,\s]|$)", lowered):
        tags.append("code_only_execution_uncertain")
    if re.search(r"\bexecute\s*=\s*false\b", lowered):
        tags.append("execute_false")
    return sorted(set(tags))


def split_picture_source(body):
    """Return drawing and surrounding source, or (None, None) if malformed.

    Keep nested pictures in the outer payload. This is a lexical screening
    helper, not a TeX expansion/parser or proof that a drawing is pure.
    """
    clean = strip_comments(body)
    depth, start = 0, 0
    parts, outside, cursor = [], [], 0
    for match in _PICTURE.finditer(clean):
        if match[1] == "begin":
            if depth == 0:
                start = match.start()
                outside.append(clean[cursor:start])
            depth += 1
        else:
            if depth == 0:
                return None, None
            depth -= 1
            if depth == 0:
                parts.append(clean[start:match.end()])
                cursor = match.end()
    outside.append(clean[cursor:])
    return (None, None) if depth else ("\n".join(parts), "\n".join(outside))


def drawing_source(body):
    """Return complete outer picture payloads, or None if malformed."""
    return split_picture_source(body)[0]


def screen_example(example):
    """Automatically exclude unsupported/hazardous cases; never grant eligibility.

    Setup and pre/post hooks remain live, so report their hints separately
    from hazards inside skipped pictures. A Luna/source review must decide
    whether local definitions, external dependencies and context are safe.
    """
    options = strip_comments(example["options"])
    raw_body = example["body"]
    clean_body = strip_comments(raw_body)
    raw_markers = [match[1] for match in _PICTURE.finditer(raw_body)]
    clean_markers = [match[1] for match in _PICTURE.finditer(clean_body)]
    marker_mismatch = raw_markers != clean_markers
    drawing, outside = split_picture_source(raw_body)
    hints = hazard_tags("", drawing or "")
    option_hints = hazard_tags(options, "")
    if re.search(r"(?:^|,)\s*(?:code only|setup code|multipage|leave comments)(?:\s*(?:,|$))|"
                 r"(?:^|,)\s*(?:execute(?: code)?\s*=\s*false|imagesource\s*=|from file\s*=|render instead\s*=)", options):
        status, reason = "live", "Listing, setup, external image/source, or alternate renderer; keep the original execution path."
    elif re.search(r"\\begin\s*\{\s*lateximage\*?\s*\}", options):
        status, reason = "live", "An existing lateximage wrapper owns the complete example; keep its original image envelope."
    elif re.search(r"\\end\s*\{\s*tikzpicture\s*\}\s*[A-Za-z0-9]", strip_comments(example["body"])):
        status, reason = "live", "Inline prose follows the picture; preserve the original paragraph and whitespace handling."
    elif re.search(
            r"\\end\s*\{\s*tikzpicture\s*\}[ \t]*(?:\r?\n[ \t]*)?"
            r"\\begin\s*\{\s*tikzpicture\s*\}", clean_body):
        status, reason = "live", "Adjacent pictures share one codeexample without a blank-line separator; preserve the original image spacing."
    elif marker_mismatch:
        status, reason = "live", "Raw and comment-stripped picture markers differ; source rewriting cannot safely distinguish drawing boundaries."
    elif outside and re.search(r"\\(?:foreach|pgfplotsforeachungrouped|pgfplotsinvokeforeach|loop)\b", outside):
        status, reason = "live", "A loop outside the picture may execute one rewritten template repeatedly with different inputs; keep it live."
    elif drawing is None:
        status, reason = "live", "Unbalanced picture boundaries; source rewriting is unsupported."
    elif not drawing:
        status, reason = "live", "No supported outer tikzpicture environment; keep the original execution path."
    elif hints:
        status, reason = "review", "Drawing has lexical hazard hints; check their scope and dependencies before opting in."
    else:
        status, reason = "review", "No lexical drawing hazard found; context and macro effects still require source review."
    return {"status": status, "reason": reason,
            "drawing_hazards": hints, "option_hazards": option_hints}


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
        example = {
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
        example["screening"] = screen_example(example)
        yield example
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


def scoped_cache_id(example):
    material = ("render-cache-v2\0" + example["file"] + "\0" +
                str(example["ordinal"]) + "\0" + example["source_span_sha256"])
    return hashlib.sha256(material.encode()).hexdigest()


PROSE_POLICY = "tex-prose-v1"


def _protect_document_code(source, prose_envs):
    """Keep verbatim/example/unknown environments byte-exact, including %."""
    begin_pattern = re.compile(r"\\begin\s*\{([^{}]+)\}")
    edits, cursor = [], 0
    while (begin := _find_token(begin_pattern, source, cursor)) is not None:
        name = begin[1]
        cursor = begin.end()
        if name in prose_envs:
            continue
        pattern = re.compile(r"\\(begin|end)\s*\{" + re.escape(name) + r"\}")
        depth = 1
        # Raw matching also respects verbatim end markers, where % is data.
        for end in pattern.finditer(source, cursor):
            depth += 1 if end[1] == "begin" else -1
            if depth == 0:
                payload = source[begin.start():end.end()]
                edits.append((begin.start(), end.end(), "<protected-" + hashlib.sha256(payload.encode("utf-8", errors="surrogateescape")).hexdigest() + ">"))
                cursor = end.end()
                break
        else:
            return None
    for start, end, replacement in reversed(edits):
        source = source[:start] + replacement + source[end:]
    return source


def _remove_tex_comments(source):
    result, cursor = [], 0
    while cursor < len(source):
        end = _comment_end(source, cursor)
        if end is None:
            result.append(source[cursor])
            cursor += 1
        else:
            # A TeX comment consumes its newline, including inside definitions.
            cursor = end + (end < len(source))
    return "".join(result)


def prose_independent_source(source):
    """Ignore only plain prose outside groups and executable environments.

    This is deliberately not a TeX interpreter: macro arguments, examples,
    unknown commands/environments and their continuations remain exact. New
    commands in previously plain prose therefore invalidate the review.
    """
    prose_envs = {"document", "itemize", "enumerate", "description", "quote", "quotation",
                  "center", "flushleft", "flushright", "abstract", "multicols"}
    protected_source = _protect_document_code(source, prose_envs)
    if protected_source is None:
        return source
    clean = _remove_tex_comments(protected_source)
    plain = re.compile(r"[A-Za-z][A-Za-z0-9 \t\n.,;:!?\"'()–—-]*\Z")
    tokens = re.compile(r"\\(?:begin|end)\s*\{([^{}]+)\}|\\.|[{}]")
    depth, stack, result = 0, [], []
    # Blank-line boundaries are significant inside code/groups, but line
    # wrapping within an ordinary paragraph is not executable setup.
    for match in re.finditer(r"([\s\S]*?)(\n[ \t]*\n|\Z)", clean):
        paragraph, separator = match.groups()
        if not paragraph and not separator:
            continue
        protected = depth > 0 or any(name not in prose_envs for name in stack)
        for token in tokens.finditer(paragraph):
            value = token.group()
            if token[1] is not None:
                if value.startswith(r"\begin"):
                    stack.append(token[1])
                elif stack and stack[-1] == token[1]:
                    stack.pop()
                else:
                    # Unknown/malformed nesting cannot establish prose scope.
                    return source
            elif value == "{":
                depth += 1
            elif value == "}":
                depth -= 1
                if depth < 0:
                    return source
        if not protected and depth == 0 and not any(name not in prose_envs for name in stack):
            text = paragraph.strip()
            if plain.fullmatch(text) and len(text.split()) >= 2:
                paragraph = "<plain prose>"
        result.append(paragraph + separator)
    if depth or stack:
        # Included chapters may omit the document environment, but genuine
        # unterminated groups/other environments must stay exact.
        return source
    return "".join(result).strip()


def context_fingerprint(docdir, policy="exact-v1"):
    root = Path(docdir)
    prefix = b"illustration-review-context-v1\0" if policy == "exact-v1" else b"illustration-review-context-prose-v1\0"
    if policy not in ("exact-v1", PROSE_POLICY):
        raise ValueError("Unknown illustration context policy: " + policy)
    digest = hashlib.sha256(prefix)
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".tex", ".sty", ".cfg", ".lua"}:
            content = path.read_bytes()
            if policy == PROSE_POLICY and path.suffix == ".tex":
                content = prose_independent_source(content.decode("utf-8", errors="surrogateescape")).encode("utf-8", errors="surrogateescape")
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def implementation_fingerprint(tree, docdir):
    """Package code outside the documentation must not silently change."""
    tree, docs = Path(tree), (Path(tree) / docdir).resolve()
    digest = hashlib.sha256(b"illustration-package-code-v1\0")
    for path in sorted(tree.rglob("*")):
        if (path.is_file() and not path.resolve().is_relative_to(docs)
                and path.suffix in {".tex", ".sty", ".cls", ".clo", ".cfg", ".def", ".dtx", ".lua"}):
            digest.update(path.relative_to(tree).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def upgrade_manifest(docdir, manifest, implementation_sha256):
    """Migrate existing decisions only at their exact previously reviewed tree."""
    if manifest.get("context_policy", "exact-v1") != "exact-v1":
        raise ValueError("Manifest already uses a scoped context policy")
    if manifest.get("context_sha256") != context_fingerprint(docdir):
        raise ValueError("Cannot migrate stale review: exact original context required")
    current = {(e["file"], e["line"], e["source_sha256"], e["source_span_sha256"]): e["ordinal"]
               for e in enumerate_examples(docdir)}
    if any(tuple(e.get(k) for k in ("file", "line", "source_sha256", "source_span_sha256")) not in current
           for e in manifest["examples"]):
        raise ValueError("Cannot migrate stale example decisions")
    return dict(manifest, format=2, context_policy=PROSE_POLICY,
                legacy_context_sha256=manifest["context_sha256"],
                context_sha256=context_fingerprint(docdir, PROSE_POLICY),
                implementation_sha256=implementation_sha256,
                examples=[dict(e, ordinal=current[tuple(e.get(k) for k in
                          ("file", "line", "source_sha256", "source_span_sha256"))]) for e in manifest["examples"]])


def apply_cache_tags(docdir, audit_manifest, implementation_sha256=None):
    """Insert render-cache options only for exact, reviewed eligible examples.

    Legacy manifests match file, line and both hashes. Scoped manifests match
    file, ordinal and exact span, with a prose-independent global context and
    exact package implementation. Apply edits backwards to preserve offsets.
    """
    root = Path(docdir)
    by_location = {}
    records = audit_manifest.get("examples", [])
    manifest_context = audit_manifest.get("context_sha256")
    policy = audit_manifest.get("context_policy", "exact-v1")
    if (not isinstance(manifest_context, str) or not manifest_context.strip() or
            manifest_context != context_fingerprint(root, policy) or
            (policy == PROSE_POLICY and (not implementation_sha256 or
             audit_manifest.get("implementation_sha256") != implementation_sha256))):
        return {"tagged": 0, "stale": sum(r.get("status") == "eligible" for r in records),
                "ineligible": 0}
    for record_id, record in enumerate(records):
        key = (record.get("file"), (record.get("ordinal"), record.get("source_span_sha256")) if policy == PROSE_POLICY else record.get("line"))
        by_location.setdefault(key, []).append((record_id, record))

    grouped = {}
    counts = {"tagged": 0, "stale": 0, "ineligible": 0}
    matched_manifest_ids = set()
    for example in enumerate_examples(root):
        location = (example["ordinal"], example["source_span_sha256"]) if policy == PROSE_POLICY else example["line"]
        candidates = by_location.get((example["file"], location), [])
        if not candidates:
            continue
        matching = [(record_id, record) for record_id, record in candidates
                    if (policy == PROSE_POLICY or record.get("source_sha256") == example["source_sha256"]) and
                    record.get("source_span_sha256") == example["source_span_sha256"]]
        if not matching:
            if not any(record.get("status") == "eligible" for _, record in candidates):
                counts["ineligible"] += 1
            continue
        for record_id, record in matching:
            if record.get("status") == "eligible":
                matched_manifest_ids.add(record_id)
        record_id, record = matching[0]
        # Conflicting duplicate reviews must never be resolved by list order.
        # A reviewed hazard/uncertainty always keeps the original execution.
        if (any(candidate.get("status") != "eligible" for _, candidate in matching)
                or not drawing_source(example["body"])
                or screen_example(example)["status"] == "live"):
            counts["ineligible"] += 1
            continue
        if "render cache=" in example["options"]:
            # Existing hand-authored cache settings must not be overwritten.
            counts["ineligible"] += 1
            continue
        insertion = example["options_end"] - 1 if example["has_options"] else example["begin_end"]
        identity = scoped_cache_id(example) if policy == PROSE_POLICY else cache_id(example)
        option = ("," if example["has_options"] and example["options"].strip() else "") + "render cache=" + identity
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


def build_inventory(package, docdir, policy="exact-v1", implementation_sha256=None):
    root = Path(docdir)
    examples = list(enumerate_examples(root))
    return {
        "package": package,
        "docdir": str(root.resolve()),
        "context_sha256": context_fingerprint(root, policy),
        "context_policy": policy,
        "implementation_sha256": implementation_sha256,
        "examples": examples,
        "screening_summary": {
            status: sum(e["screening"]["status"] == status for e in examples)
            for status in ("live", "review")
        },
    }


def merge_reviews(inventory, reviews, upstream_commit):
    """Build a complete, fingerprint-checked manifest from independent reviews.

    Negative findings take precedence over positive findings. Regex screening
    never approves a drawing; missing decisions remain explicitly unreviewed.
    """
    fields = ("file", "line", "source_sha256", "source_span_sha256")
    if inventory.get("context_policy") == PROSE_POLICY:
        fields += ("ordinal",)
    statuses = ("unsafe", "uncertain", "listing_only", "unsupported", "unreviewed", "eligible")
    indexed = {tuple(example[field] for field in fields): example
               for example in inventory["examples"]}
    decisions = {}
    policy = inventory.get("context_policy", "exact-v1")
    for review in reviews:
        if review.get("package") != inventory["package"]:
            raise ValueError("review package does not match inventory")
        if any(record.get("status") == "eligible" for record in review.get("examples", [])):
            if review.get("context_policy", "exact-v1") != policy:
                raise ValueError("Review context policy differs from the inventory")
            if policy == PROSE_POLICY and (not inventory.get("implementation_sha256") or
                    review.get("implementation_sha256") != inventory.get("implementation_sha256")):
                raise ValueError("Package implementation changed since the review")
        review_context = review.get("context_sha256")
        if (review_context is not None and
                (not isinstance(review_context, str) or not review_context.strip() or
                 review_context != inventory["context_sha256"])):
            raise ValueError("stale review context: shared sources changed since the review")
        if (not isinstance(review_context, str) or not review_context.strip()) and any(
                record.get("status") == "eligible" for record in review.get("examples", [])):
            raise ValueError("positive review decisions require a matching context_sha256")
        for record in review["examples"]:
            key = tuple(record.get(field) for field in fields)
            if key not in indexed:
                raise ValueError(f"stale or unknown review: {record.get('file')}:{record.get('line')}")
            if record.get("status") not in statuses or not str(record.get("reason", "")).strip():
                raise ValueError(f"review needs a recognized status and reason: {key[:2]}")
            previous = decisions.get(key)
            if previous is None or statuses.index(record["status"]) < statuses.index(previous["status"]):
                decisions[key] = dict(record, reviewer=record.get("reviewer", review.get("reviewer", "source review")))
    records = []
    for key, example in indexed.items():
        record = {field: example[field] for field in fields}
        decision = decisions.get(key)
        if decision is None:
            record.update(status="unreviewed", reason="No source-review decision; execute normally.")
        else:
            for field in ("status", "reason", "evidence", "reviewer"):
                if field in decision:
                    record[field] = decision[field]
            if record["status"] == "eligible" and screen_example(example)["status"] == "live":
                record.update(status="unsupported", reason=screen_example(example)["reason"])
        records.append(record)
    return {
        "format": 2 if policy == PROSE_POLICY else 1, "package": inventory["package"], "upstream_commit": upstream_commit,
        "context_sha256": inventory["context_sha256"],
        "context_policy": policy,
        "implementation_sha256": inventory.get("implementation_sha256"),
        "enabled": True,
        "scope": "Drawing payloads only, between LaTeX passes of one freshly prepared build. Setup, hooks and listings remain live.",
        "default": "uncached",
        "review": "Luna source reviews plus conservative automatic screening. Missing, uncertain, conflicting, unsupported or changed examples execute normally. Screening never grants eligibility.",
        "summary": dict(sorted(Counter(record["status"] for record in records).items())),
        "examples": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="package label, for example pgf")
    parser.add_argument("docdir", type=Path, help="prepared manual documentation directory")
    parser.add_argument("--output", "-o", type=Path, help="JSON inventory destination")
    parser.add_argument("--context-policy", choices=["exact-v1", PROSE_POLICY], default=PROSE_POLICY)
    parser.add_argument("--source-root", type=Path, help="prepared exported upstream tree (before docdir)")
    parser.add_argument("--upgrade-manifest", type=Path,
                        help="migrate an existing review at its exact original source/context; no new approvals")
    parser.add_argument("--review", type=Path, action="append", default=[],
                        help="fingerprint-matched source review JSON (repeat for independent batches)")
    parser.add_argument("--manifest-output", type=Path,
                        help="also write a complete audit manifest from the supplied reviews")
    parser.add_argument("--upstream-commit", help="upstream revision covered by the reviews")
    args = parser.parse_args(argv)
    source_root = args.source_root
    lock_path = Path(__file__).resolve().parents[1] / args.package / "upstream.lock"
    values = dict(line.split("=", 1) for line in lock_path.read_text().splitlines()
                  if "=" in line and not line.startswith("#"))
    if source_root is None:
        suffix = Path(values["docdir"]).parts
        if suffix and args.docdir.resolve().parts[-len(suffix):] == suffix:
            source_root = args.docdir.resolve().parents[len(suffix) - 1]
        elif values["docdir"] == ".":
            source_root = args.docdir
        else:
            parser.error("--source-root is required for a nonstandard documentation path")
    implementation = implementation_fingerprint(source_root, values["docdir"])
    if args.upgrade_manifest:
        if not args.manifest_output:
            parser.error("--upgrade-manifest requires --manifest-output")
        old = json.loads(args.upgrade_manifest.read_text())
        if not args.upstream_commit or args.upstream_commit != old.get("upstream_commit"):
            parser.error("Migration requires the exact reviewed --upstream-commit")
        upstream = lock_path.parent.parent / ".upstream" / args.package
        actual_commit = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
        if actual_commit != args.upstream_commit:
            parser.error("Fetch the exact reviewed upstream commit before migrating")
        try:
            upgraded = upgrade_manifest(args.docdir, old, implementation)
        except ValueError as error:
            parser.error(str(error))
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(upgraded, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Preserved existing review decisions with the prose-independent context policy")
        return
    if not args.output:
        parser.error("--output is required for an inventory")
    inventory = build_inventory(args.package, args.docdir, args.context_policy, implementation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(inventory['examples'])} examples to {args.output}")
    print("Automatic screening:", json.dumps(inventory["screening_summary"], sort_keys=True))
    if args.manifest_output:
        if not args.upstream_commit or not re.fullmatch(r"[a-f0-9]{40}", args.upstream_commit):
            parser.error("--manifest-output requires a full --upstream-commit SHA")
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in args.review]
        try:
            manifest = merge_reviews(inventory, reviews, args.upstream_commit)
        except ValueError as exc:
            parser.error(str(exc))
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Review decisions:", json.dumps(manifest["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
