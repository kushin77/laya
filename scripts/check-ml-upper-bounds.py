#!/usr/bin/env python3
"""Fail loudly if a documented ML dependency upper bound has been raised.

engine/requirements-ml.txt pins upper bounds on a few packages based on
empirical breakage (see the comments next to each pin there): a wheel floor,
a removed API, etc. Nothing stops someone from editing the `<X` bound in that
file without redoing the research or test-suite check that justified it in
the first place.

This script holds its own copy of the last-verified ceiling for those
packages. It parses the *current* upper bound out of requirements-ml.txt and
fails if it is higher than the last-verified one, i.e. if a relock could now
cross a bound nobody has re-verified.

Raising a bound on purpose means: do the verification (or re-read the
comment's reasoning and confirm it no longer applies), then update BOTH
requirements-ml.txt and VERIFIED_CEILINGS below in the same change.

Run from the repo root:
    python3 scripts/check-ml-upper-bounds.py
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_ML = REPO_ROOT / "engine" / "requirements-ml.txt"

# The highest upper bound that has actually been verified safe, per package.
# Keep these in step with the comments in requirements-ml.txt.
VERIFIED_CEILINGS = {
    "torch": "2.12",
    "transformers": "5.17",
}


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse_upper_bound(package: str) -> str | None:
    pattern = re.compile(
        rf"^{re.escape(package)}\s*[><=~!,.\w\s]*?,\s*<\s*([0-9][0-9.]*)",
        re.MULTILINE,
    )
    match = pattern.search(REQUIREMENTS_ML.read_text())
    return match.group(1) if match else None


def main() -> int:
    if not REQUIREMENTS_ML.exists():
        print(f"ERROR: {REQUIREMENTS_ML} not found", file=sys.stderr)
        return 1

    status = 0
    for package, verified_ceiling in VERIFIED_CEILINGS.items():
        documented_bound = parse_upper_bound(package)
        if documented_bound is None:
            print(
                f"ERROR: {package} has a verified ceiling of {verified_ceiling} "
                f"in {Path(__file__).name}, but no '<X' upper bound was found "
                f"for it in {REQUIREMENTS_ML.relative_to(REPO_ROOT)}. Update "
                "this script if the constraint was intentionally removed.",
                file=sys.stderr,
            )
            status = 1
            continue

        if version_tuple(documented_bound) > version_tuple(verified_ceiling):
            print(
                f"ERROR: {package}'s upper bound in "
                f"{REQUIREMENTS_ML.relative_to(REPO_ROOT)} is now <{documented_bound}, "
                f"which is past the last-verified ceiling of <{verified_ceiling}. "
                "A relock could pick up a version that reintroduces the breakage "
                "documented next to that pin. Re-verify (or confirm the reasoning "
                "no longer applies), then raise VERIFIED_CEILINGS in "
                f"{Path(__file__).name} to match.",
                file=sys.stderr,
            )
            status = 1
        else:
            print(f"OK {package}: documented bound <{documented_bound} <= verified ceiling <{verified_ceiling}")

    return status


if __name__ == "__main__":
    sys.exit(main())
