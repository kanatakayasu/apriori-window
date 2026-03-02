from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


def _resolve_spmf_jar(jar_path: Optional[str] = None) -> Path:
    if jar_path:
        p = Path(jar_path)
    else:
        env = os.environ.get("SPMF_JAR", "")
        p = Path(env) if env else Path("spmf.jar")
    if not p.exists():
        raise FileNotFoundError(
            f"SPMF jar not found: {p}. Set SPMF_JAR or pass jar_path."
        )
    return p


def run_spmf(
    algorithm: str,
    input_path: Path,
    output_path: Path,
    args: List[str],
    jar_path: Optional[str] = None,
) -> Dict[str, str]:
    jar = _resolve_spmf_jar(jar_path)
    cmd = [
        "java",
        "-jar",
        str(jar),
        "run",
        algorithm,
        str(input_path),
        str(output_path),
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "cmd": " ".join(cmd),
        "returncode": str(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def write_temp_spmf_input(lines: List[str]) -> Path:
    fd, tmp = tempfile.mkstemp(prefix="cmp_methods_", suffix=".txt")
    os.close(fd)
    p = Path(tmp)
    with open(p, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line)
            f.write("\n")
    return p
