from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict

from .adapters.spmf import run_spmf


def check_python() -> Dict[str, str]:
    return {"ok": "true", "detail": shutil.which("python3") or "python3"}


def check_java() -> Dict[str, str]:
    java = shutil.which("java")
    if not java:
        return {"ok": "false", "detail": "java not found"}
    proc = subprocess.run([java, "-version"], capture_output=True, text=True, check=False)
    return {
        "ok": "true" if proc.returncode == 0 else "false",
        "detail": (proc.stderr or proc.stdout).splitlines()[0] if (proc.stderr or proc.stdout) else "unknown",
    }


def check_spmf(jar_path: str | None = None) -> Dict[str, str]:
    p = Path(jar_path) if jar_path else Path(os.environ.get("SPMF_JAR", "spmf.jar"))
    if not p.exists():
        return {"ok": "false", "detail": f"jar not found: {p}"}

    # Smoke test by running Apriori on tiny DB.
    fd_in, in_path = tempfile.mkstemp(prefix="cmp_chk_in_", suffix=".txt")
    fd_out, out_path = tempfile.mkstemp(prefix="cmp_chk_out_", suffix=".txt")
    os.close(fd_in)
    os.close(fd_out)
    Path(in_path).write_text("1 2\n1 3\n", encoding="utf-8")
    Path(out_path).write_text("", encoding="utf-8")
    try:
        info = run_spmf(
            algorithm="Apriori",
            input_path=Path(in_path),
            output_path=Path(out_path),
            args=["0.5"],
            jar_path=str(p),
        )
        ok = info["returncode"] == "0"
        return {
            "ok": "true" if ok else "false",
            "detail": "smoke ok" if ok else (info["stderr"] or info["stdout"]).strip()[:300],
        }
    finally:
        Path(in_path).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)


def check_pami() -> Dict[str, str]:
    try:
        import PAMI  # type: ignore
        from PAMI.partialPeriodicFrequentPattern.basic import GPFgrowth as mod  # type: ignore
    except Exception as e:
        return {"ok": "false", "detail": f"import failed: {e}"}

    classes = [name for name in ("GPFgrowth", "GPFGrowth") if hasattr(mod, name)]
    return {
        "ok": "true" if classes else "false",
        "detail": f"PAMI import ok; classes={classes}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check comparative backends")
    parser.add_argument("--spmf-jar", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    report = {
        "python": check_python(),
        "java": check_java(),
        "spmf": check_spmf(args.spmf_jar),
        "pami": check_pami(),
    }

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("[backend-check]")
    for k, v in report.items():
        print(f"- {k}: ok={v['ok']} detail={v['detail']}")


if __name__ == "__main__":
    main()
