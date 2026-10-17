#!/usr/bin/env python3
"""Assemble the source tree a package's manual is built from.

    scripts/prepare.py <package>                   -> build/<package>/src
    scripts/prepare.py <package> --dest DIR
    scripts/prepare.py <package> --reject           (apply failing patches partially)
    scripts/prepare.py <package> --refresh-patches DIR

The tree is: the upstream sources (from .upstream/<package>, see fetch.sh) at
the checked-out commit, then <package>/preprocess.py (if any) run on it, then
<package>/patches/*.patch applied, then the files of <package>/ copied into the
upstream documentation directory (`docdir` in upstream.lock), then shared/.

--refresh-patches DIR rewrites <package>/patches/ from a tree in which upstream
files were edited (e.g. build/<package>/src after fixing a conflict, or a
checkout of an old fork): one patch per upstream file that differs from the
preprocessed upstream version. Files that do not exist upstream are ignored;
they belong in <package>/.
"""
import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

from illustration_audit import apply_cache_tags

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
# files of <package>/ that are not copied into the build tree
OWN_FILES = {"upstream.lock", "preprocess.py", "patches", "build", "README.md", ".gitignore", "__pycache__", "illustration-audit.json"}


def read_lock(pkg):
    lock = {}
    with open(os.path.join(ROOT, pkg, "upstream.lock")) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                lock[key] = value
    return lock


def export_upstream(pkg, dest):
    """Upstream files at the checked-out commit (without .git) into dest."""
    upstream = os.path.join(ROOT, ".upstream", pkg)
    if not os.path.isdir(os.path.join(upstream, ".git")):
        sys.exit(f"missing {upstream}; run scripts/fetch.sh {pkg}")
    os.makedirs(dest)
    archive = subprocess.run(["git", "-C", upstream, "archive", "--format=tar", "HEAD"],
                             check=True, capture_output=True).stdout
    with tempfile.TemporaryFile() as f:
        f.write(archive)
        f.seek(0)
        with tarfile.open(fileobj=f) as tar:
            tar.extractall(dest, filter="tar")


def preprocess(pkg, tree):
    script = os.path.join(ROOT, pkg, "preprocess.py")
    if os.path.exists(script):
        subprocess.run([sys.executable, script, tree], check=True)


def patch_files(pkg):
    d = os.path.join(ROOT, pkg, "patches")
    return sorted(os.path.join(d, p) for p in os.listdir(d) if p.endswith(".patch")) if os.path.isdir(d) else []


def apply_patches(pkg, tree, reject=False):
    failed = []
    for patch in patch_files(pkg):
        # GIT_CEILING_DIRECTORIES: treat the tree as plain files even inside a
        # repository (otherwise git apply silently skips paths "outside" it)
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(tree))
        cmd = ["git", "apply", "--verbose", "--whitespace=nowarn", "-p1"] + (["--reject"] if reject else [])
        res = subprocess.run(cmd + [patch], cwd=tree, capture_output=True, text=True, env=env)
        if res.returncode or "Skipped patch" in res.stderr:
            failed.append((os.path.basename(patch), res.stderr.strip()))
    if failed and reject:
        rejects = [os.path.relpath(os.path.join(d, f), tree)
                   for d, _, fs in os.walk(tree) for f in fs if f.endswith(".rej")]
        print(f"{len(failed)} patches applied partially; resolve by hand:", *sorted(rejects), sep="\n  ")
    elif failed:
        for name, err in failed:
            print(f"patch {name} does not apply:\n  {err}", file=sys.stderr)
        sys.exit(f"{len(failed)} patches failed; see 'Fixing a patch' in README.md")


def overlay(pkg, tree, docdir):
    target = os.path.join(tree, docdir)
    # PGF-style manuals share their HTML documentation vocabulary. Keep these
    # helpers selective: PGFplots has its own variants of some of these files.
    documentation = read_lock(pkg).get("documentation")
    if documentation:
        shutil.copytree(os.path.join(SHARED, documentation + "manual"), target, dirs_exist_ok=True)
    src = os.path.join(ROOT, pkg)
    for name in os.listdir(src):
        if name in OWN_FILES or name.startswith("."):
            continue
        s, t = os.path.join(src, name), os.path.join(target, name)
        if os.path.isdir(s):
            shutil.copytree(s, t, dirs_exist_ok=True)
        else:
            shutil.copy2(s, t)
    for name in os.listdir(SHARED):
        if not os.path.isfile(os.path.join(SHARED, name)) or name.startswith("."):
            continue
        shutil.copy2(os.path.join(SHARED, name), target)


def prepare(pkg, dest, patches=True, reject=False, illustration_cache=True):
    lock = read_lock(pkg)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    export_upstream(pkg, dest)
    preprocess(pkg, dest)
    if patches:
        apply_patches(pkg, dest, reject)
    overlay(pkg, dest, lock["docdir"])
    audit = os.path.join(ROOT, pkg, "illustration-audit.json")
    if patches and illustration_cache and os.path.isfile(audit):
        with open(audit) as stream:
            review = json.load(stream)
        commit = subprocess.check_output(
            ["git", "-C", os.path.join(ROOT, ".upstream", pkg), "rev-parse", "HEAD"],
            text=True).strip()
        if not review.get("enabled", True):
            print(f"{pkg}: drawing cache disabled by illustration review policy")
        elif review.get("upstream_commit") != commit:
            print(f"{pkg}: upstream changed since illustration review; drawing cache disabled")
        else:
            counts = apply_cache_tags(os.path.join(dest, lock["docdir"]), review)
            print(f"{pkg}: illustration review: {counts['tagged']} cache candidates, "
                  f"{counts['stale']} changed examples left uncached")


def refresh_patches(pkg, edited):
    root_docs = read_lock(pkg)["docdir"] == "."
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "base")
        export_upstream(pkg, base)
        preprocess(pkg, base)
        changed = []
        for dirpath, _, files in os.walk(base):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), base)
                other = os.path.join(edited, rel)
                if os.sep not in rel and not root_docs:
                    continue  # repository files (README.md, ...), not part of the manual
                if os.path.exists(other) and not filecmp.cmp(os.path.join(base, rel), other, shallow=False):
                    changed.append(rel)
        outdir = os.path.join(ROOT, pkg, "patches")
        if os.path.isdir(outdir):
            shutil.rmtree(outdir)
        os.makedirs(outdir)
        basenames = [rel.split("/")[-1] for rel in changed]
        for rel in sorted(changed):
            diff = subprocess.run(
                ["git", "diff", "--no-index", "--no-color", "--src-prefix=a/", "--dst-prefix=b/",
                 os.path.join(base, rel), os.path.join(edited, rel)],
                capture_output=True).stdout
            # make the paths relative to the tree root
            diff = diff.replace(("a" + os.path.join(base, rel)).encode(), ("a/" + rel).encode())
            diff = diff.replace(("b" + os.path.join(edited, rel)).encode(), ("b/" + rel).encode())
            diff = b"\n".join(l for l in diff.split(b"\n") if not l.startswith(b"index "))
            name = rel.split("/")[-1]
            if basenames.count(name) > 1:
                name = rel.replace("/", "--")
            name += ".patch"
            with open(os.path.join(outdir, name), "wb") as f:
                f.write(diff)
        print(f"wrote {len(changed)} patches to {os.path.relpath(outdir, ROOT)}/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--dest")
    ap.add_argument("--no-patches", action="store_true")
    ap.add_argument("--no-illustration-cache", action="store_true",
                    help="prepare untagged sources for illustration review")
    ap.add_argument("--reject", action="store_true",
                    help="apply what applies of failing patches, leave .rej files and continue")
    ap.add_argument("--refresh-patches", metavar="DIR")
    args = ap.parse_args()
    if args.refresh_patches:
        refresh_patches(args.package, os.path.abspath(args.refresh_patches))
    else:
        dest = os.path.abspath(args.dest or os.path.join(ROOT, "build", args.package, "src"))
        prepare(args.package, dest, patches=not args.no_patches, reject=args.reject,
                illustration_cache=not args.no_illustration_cache)
        print(f"{args.package}: source tree in {os.path.relpath(dest, ROOT)}")


if __name__ == "__main__":
    main()
