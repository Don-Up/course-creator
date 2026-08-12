from pathlib import Path
import subprocess


def test_production_source_size_gate_passes():
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["node", "scripts/check-source-size.mjs"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
