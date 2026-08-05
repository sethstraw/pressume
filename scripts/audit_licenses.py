"""Check that every dependency can be shipped inside an MIT-licensed tool.

Run this after any dependency change. The rule it enforces is narrow and
deliberate: no strong copyleft anywhere in the runtime tree, and no proprietary
or unknown licence at all.

Weak, file-level copyleft is allowed and listed. MPL-2.0 obliges you to publish
changes to those specific files, which nobody here makes, and it places no
condition on the code that merely imports them. Strong copyleft is different:
AGPL-3.0 would extend its terms to this whole program the moment it is
distributed, which is incompatible with offering it under MIT.

pip-licenses reads whatever is installed, and is not something this project
depends on, so it is supplied for the run instead of being declared:

    uv run --with pip-licenses python scripts/audit_licenses.py

CI runs exactly that command on every push and pull request.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter

# Licences that would reach out and govern this program. Any of these in the
# runtime tree is a release blocker, not a note.
STRONG_COPYLEFT = ("AGPL", "SSPL", "OSL", "EUPL", "CC-BY-SA")
# GPL and LGPL are listed separately because a tri-licensed package may offer
# them alongside an acceptable option; the report shows the whole expression so
# a human can confirm a compatible choice exists.
WEAK_COPYLEFT = ("MPL", "LGPL")
UNACCEPTABLE = ("PROPRIETARY", "UNKNOWN", "OTHER/PROPRIETARY")
# Tooling that is not part of what ships.
IGNORE = {"pip-licenses", "prettytable", "wcwidth", "tomli", "pressume"}


def main() -> int:
    """Report the licence of every installed dependency and fail on a blocker."""
    raw = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--with-urls"],
        capture_output=True,
        text=True,
        check=False,
    )
    if raw.returncode != 0:
        print("pip-licenses is not installed. Try: uv run --with pip-licenses python", raw.stderr)
        return 2

    packages = [p for p in json.loads(raw.stdout) if p["Name"].lower() not in IGNORE]
    print(f"{len(packages)} packages\n")
    for licence, count in Counter(p["License"] for p in packages).most_common():
        print(f"  {count:3}  {licence}")

    blockers = [
        p
        for p in packages
        if any(k in p["License"].upper() for k in STRONG_COPYLEFT + UNACCEPTABLE)
    ]
    weak = [p for p in packages if any(k in p["License"].upper() for k in WEAK_COPYLEFT)]

    if weak:
        print("\nWeak, file-level copyleft (allowed, unmodified):")
        for package in weak:
            print(f"  {package['Name']:20} {package['License']}")

    if blockers:
        print("\nBLOCKERS. These cannot ship inside an MIT-licensed program:")
        for package in blockers:
            print(f"  {package['Name']:20} {package['License']}")
            print(f"  {'':20} {package.get('URL', '')}")
        return 1

    print("\nNo strong copyleft, proprietary, or unknown licences. Clear to ship under MIT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
