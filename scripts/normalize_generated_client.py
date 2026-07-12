#!/usr/bin/env python3
"""Normalise the OpenAPI Generator TypeScript client output.

The pinned ``@openapitools/openapi-generator-cli`` (v7.23.0) emits a small
amount of trailing whitespace and sometimes a duplicated final newline in
``.ts`` and ``.md`` files. ``git diff --check`` rejects these as whitespace
errors, which would break ``git diff --cached --check`` for any commit that
includes the regenerated client.

This normalizer is a deterministic post-processing pass that strips trailing
whitespace from every line and ensures the file ends with exactly one
newline. It runs as part of ``scripts/generate_frontend_api_client.sh`` so
the canonical generation pipeline never emits whitespace warnings.

Usage:

    python scripts/normalize_generated_client.py \
        [--root frontend/src/generated/k9b-api] [--check]

With ``--check``, the script exits 1 if any file would be changed and prints
the offending paths. Without ``--check``, files are rewritten in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# File suffixes produced by the typescript-fetch template that we accept
# as generated outputs. We deliberately exclude binary / managed files.
GENERATED_SUFFIXES: tuple[str, ...] = (".ts", ".md", ".json")


def normalise(text: str) -> str:
    """Strip trailing whitespace from every line and enforce a single
    trailing newline.

    The output is deterministic for a given input: we apply the same set of
    transformations every run, so regeneration + normalisation produces
    byte-stable output as long as the OpenAPI Generator template does not
    change.
    """
    # Strip trailing whitespace per line.
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    # Collapse any trailing blank lines into a single newline terminator.
    if cleaned:
        cleaned = cleaned.rstrip("\n") + "\n"
    else:
        cleaned = "\n"
    return cleaned


def iter_generated_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in GENERATED_SUFFIXES
        and ".openapi-generator" not in path.parts
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("frontend/src/generated/k9b-api"),
        help="Root directory of the generated TypeScript client "
        "(default: frontend/src/generated/k9b-api)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any file would change; do not rewrite.",
    )
    args = parser.parse_args()

    changed: list[Path] = []
    for path in iter_generated_files(args.root):
        original = path.read_text(encoding="utf-8")
        rewritten = normalise(original)
        if original != rewritten:
            changed.append(path)
            if not args.check:
                path.write_text(rewritten, encoding="utf-8")

    if changed:
        verb = "would change" if args.check else "normalised"
        sys.stderr.write(f"{verb} {len(changed)} generated file(s):\n")
        for path in changed:
            sys.stderr.write(f"  {path}\n")
        return 1 if args.check else 0
    sys.stderr.write("no whitespace drift detected\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
