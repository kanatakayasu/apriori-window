from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict


def _crate_dir() -> Path:
    # Use the existing apriori_window_suite crate so we can build offline with cached deps.
    return Path(__file__).resolve().parents[3] / "apriori_window_suite"


def _bin_path() -> Path:
    return _crate_dir() / "target" / "release" / "comparative_mining"


def ensure_rust_binary() -> Path:
    bin_path = _bin_path()
    if bin_path.exists():
        return bin_path

    crate = _crate_dir()
    proc = subprocess.run(
        ["cargo", "build", "--release", "--offline", "--bin", "comparative_mining"],
        cwd=str(crate),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "failed to build comparative_mining rust binary:\n"
            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )

    if not bin_path.exists():
        raise FileNotFoundError(f"compiled binary not found: {bin_path}")
    return bin_path


def run_rust_mining(
    method: str,
    input_path: Path,
    input_format: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    bin_path = ensure_rust_binary()
    params_json = json.dumps(params, ensure_ascii=False)

    cmd = [
        str(bin_path),
        "--method",
        method,
        "--input",
        str(input_path),
        "--input-format",
        input_format,
        "--params-json",
        params_json,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"rust mining failed (method={method})\n"
            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )

    try:
        out = json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError(f"failed to parse rust output as json: {e}\n{proc.stdout}")

    out["_runner"] = {
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "stderr": proc.stderr,
    }
    return out
