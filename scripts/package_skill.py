#!/usr/bin/env python3
"""Build the uploadable skill package for the skill marketplace.

The marketplace parser is strict about three things, and all three fail at
upload time, not at build time, which wastes a round trip each:

  1. `SKILL.md` must carry version (SemVer, three parts), display_name,
     display_name_en, description_zh, description_en, description.
  2. The archive may contain one top-level folder and at most one level of
     subfolder inside it. `references/foo.md` is fine; `examples/vault/01/x.md`
     is rejected.
  3. The archive must be under 3 MB.

So the package is not the repository. The repository carries a demo vault nested
four levels deep and a CI workflow, neither of which belongs in the upload. This
script stages an allowlist, proves the result passes the three rules, and
*zips the staged copy only after* a self-test from that copy has passed — so a
package that ships broken scripts cannot be built.

    python3 scripts/package_skill.py                  # build release/workbuddy/agent-memory-kit.zip
    python3 scripts/package_skill.py --check          # validate, build nothing (CI)
    python3 scripts/package_skill.py --out /tmp/x.zip --no-selftest

Exit codes: 0 ok, 1 a rule is violated, 2 the staged copy fails its own tests.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Allowlist. A top-level file that is not named here does not ship.
PACKAGE_FILES = ["SKILL.md"]
PACKAGE_DIRS = ["scripts", "references", "templates", "examples"]
# Dropped from the package even though the parent directory ships. Compared as
# path *parts*, not as a string prefix: on Windows str(Path) uses backslashes, so
# a "examples/demo-vault" startswith() check silently matches nothing there and
# the depth rule then fails on the very folder it was meant to drop.
EXCLUDE_PREFIXES = [("examples", "demo-vault")]

# Marketplace limits.
MAX_BYTES = 3 * 1024 * 1024
MAX_DEPTH = 2  # <top>/<sub>/<file> is the deepest allowed

REQUIRED = ["name", "version", "display_name", "display_name_en",
            "description_zh", "description_en", "description"]

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# Anything that looks like a credential must not reach a public archive.
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


class Fail(Exception):
    pass


def read_frontmatter(text: str) -> dict:
    """Minimal YAML frontmatter reader: scalars and folded/literal blocks.

    Deliberately not PyYAML — the package must build on a bare python3, the same
    constraint every other script here is held to.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise Fail("SKILL.md does not start with a --- frontmatter block")
    try:
        end = next(i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---")
    except StopIteration:
        raise Fail("SKILL.md frontmatter is never closed with ---")

    out, key, block = {}, None, None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in (">-", ">", "|", "|-"):
                block = []
                out[key] = ""
            else:
                out[key] = val.strip("\"'")
                block = None
        elif key is not None:
            if block is None:
                raise Fail(f"frontmatter: cannot parse line under {key!r}: {raw!r}")
            block.append(raw.strip())
            out[key] = " ".join(block)
        else:
            raise Fail(f"frontmatter: orphan line before any key: {raw!r}")
    return out


def check_frontmatter(meta: dict) -> list[str]:
    bad = []
    for k in REQUIRED:
        if not str(meta.get(k, "")).strip():
            bad.append(f"missing {k}")
    ver = str(meta.get("version", ""))
    if ver and not SEMVER.match(ver):
        bad.append(f'version "{ver}" is not SemVer — write 1.0.0, not {ver}')
    for k in ("display_name", "display_name_en"):
        v = str(meta.get(k, ""))
        if v and len(v) > 60:
            bad.append(f"{k} is {len(v)} chars; keep it under 60 so the card does not clip")
    return bad


def collect() -> list[Path]:
    """Every file that should ship, as paths relative to ROOT."""
    picked: list[Path] = []
    for name in PACKAGE_FILES:
        p = ROOT / name
        if not p.is_file():
            raise Fail(f"required file missing: {name}")
        picked.append(Path(name))
    for d in PACKAGE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            raise Fail(f"required directory missing: {d}/")
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if any(rel.parts[:len(ex)] == ex for ex in EXCLUDE_PREFIXES):
                continue
            if "__pycache__" in rel.parts or rel.suffix == ".pyc":
                continue
            picked.append(rel)
    return picked


def check_tree(files: list[Path]) -> list[str]:
    bad = []
    for rel in files:
        if len(rel.parts) > MAX_DEPTH:
            bad.append(f"too deep for the marketplace ({len(rel.parts)} levels, "
                       f"max {MAX_DEPTH}): {rel.as_posix()}")
    return bad


def check_contents(files: list[Path]) -> list[str]:
    bad = []
    home = str(Path.home())
    for rel in files:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET.search(text):
            bad.append(f"credential-shaped string in {rel}")
        if home and home in text:
            bad.append(f"absolute home path {home} leaked into {rel}")
    return bad


def stage(files: list[Path], dest: Path) -> Path:
    top = dest / "agent-memory-kit"
    for rel in files:
        target = top / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return top


def selftest(top: Path) -> tuple[bool, str]:
    """Run the package's own test suite from inside the staged copy.

    This is the point of staging: a package whose scripts only work because the
    repository happened to be around them is a broken package, and the upload is
    the wrong place to find that out.
    """
    py = sys.executable or "python3"
    proc = subprocess.run([py, str(top / "scripts" / "selftest.py")],
                          cwd=str(top), capture_output=True, text=True, timeout=600)
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    return proc.returncode == 0, "\n".join(tail[-6:])


def zip_tree(top: Path, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(top.rglob("*")):
            if p.is_file():
                # Explicit posix arcname: the archive format wants forward
                # slashes, and the marketplace parser is not the place to find
                # out whether zipfile normalised them for us.
                z.write(p, p.relative_to(top.parent).as_posix())
    return out.stat().st_size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="release/workbuddy/agent-memory-kit.zip")
    ap.add_argument("--check", action="store_true",
                    help="validate only; build no archive")
    ap.add_argument("--no-selftest", action="store_true",
                    help="skip running the packaged copy's tests (fast, less honest)")
    args = ap.parse_args()

    try:
        meta = read_frontmatter((ROOT / "SKILL.md").read_text(encoding="utf-8"))
        files = collect()
    except Fail as e:
        print(f"FAIL  {e}")
        return 1

    problems = check_frontmatter(meta) + check_tree(files) + check_contents(files)
    print(f"staged   {len(files)} files from the allowlist")
    print(f"version  {meta.get('version')}  ·  {meta.get('display_name')}")
    if problems:
        for p in problems:
            print(f"FAIL  {p}")
        return 1
    print("PASS    frontmatter, depth, credential scan")

    if args.check:
        print("\nVERDICT  package rules satisfied. Nothing built (--check).")
        return 0

    with tempfile.TemporaryDirectory() as td:
        top = stage(files, Path(td))
        if not args.no_selftest:
            ok, tail = selftest(top)
            print("\n--- selftest, run from the staged copy ---")
            print(tail)
            if not ok:
                print("\nVERDICT  the packaged copy fails its own tests. Nothing zipped.")
                return 2
        out = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
        size = zip_tree(top, out)

    if size > MAX_BYTES:
        print(f"FAIL  archive is {size / 1048576:.2f} MB, limit is 3.00 MB")
        out.unlink(missing_ok=True)
        return 1
    print(f"\nwrote    {out}  ({size / 1024:.0f} KB)")
    print(f"upload   open.workbuddy.cn → 发布管理 → 技能 → 创建 → 上传这个 zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
