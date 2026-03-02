from __future__ import annotations

from typing import Dict

from .method_base import ComparativeMethod
from .methods_rust import RustMethod


def build_registry() -> Dict[str, ComparativeMethod]:
    # Comparative mining is standardized to Rust backend for fair runtime comparison.
    return {
        "apriori": RustMethod("apriori", input_format="flat"),
        "fp_growth": RustMethod("fp_growth", input_format="flat"),
        "eclat": RustMethod("eclat", input_format="flat"),
        "lcm": RustMethod("lcm", input_format="flat"),
        "pfpm": RustMethod("pfpm", input_format="flat"),
        "ppfpm_gpf_growth": RustMethod("ppfpm_gpf_growth", input_format="timestamped"),
        "lpfim": RustMethod("lpfim", input_format="timestamped"),
        "lppm": RustMethod("lppm", input_format="timestamped"),
    }
