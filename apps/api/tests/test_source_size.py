from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_production_source_size_gate_passes():
    """No production source file may exceed 500 lines.

    The limit lives in `scripts/check-source-size.mjs`; the test shells out to
    it instead of re-implementing the rule, so the script and the test can
    never drift apart.  `cwd=REPO_ROOT` makes the test independent of the
    directory pytest was started from.
    """
    result = subprocess.run(
        ["node", "scripts/check-source-size.mjs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"source size gate failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
