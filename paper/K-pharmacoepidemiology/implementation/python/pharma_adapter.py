"""
ATC code conversion and transaction generation adapter.

Converts prescription data with drug names/codes into integer-coded
transactions compatible with apriori_window_basket.py.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ATCAdapter:
    """
    Adapter for converting ATC-coded prescription data into integer
    transactions for dense interval mining.
    """

    def __init__(self, atc_level: int = 3):
        """
        Args:
            atc_level: ATC hierarchy level for truncation (1-5).
                Level 1: 1 char (A), Level 2: 3 chars (A10),
                Level 3: 4 chars (A10B), Level 4: 5 chars (A10BA),
                Level 5: 7 chars (A10BA02)
        """
        if atc_level < 1 or atc_level > 5:
            raise ValueError(f"atc_level must be 1-5, got {atc_level}")
        self.atc_level = atc_level
        self._atc_to_int: Dict[str, int] = {}
        self._int_to_atc: Dict[int, str] = {}
        self._next_id: int = 1

    # ATC code length at each level
    _LEVEL_LENGTHS = {1: 1, 2: 3, 3: 4, 4: 5, 5: 7}

    def truncate_atc(self, atc_code: str) -> str:
        """Truncate ATC code to the configured hierarchy level."""
        length = self._LEVEL_LENGTHS[self.atc_level]
        truncated = atc_code[:length]
        return truncated.upper()

    def encode_atc(self, atc_code: str) -> int:
        """
        Encode an ATC code to an integer ID.
        Truncates to the configured level first.
        """
        truncated = self.truncate_atc(atc_code)
        if truncated not in self._atc_to_int:
            self._atc_to_int[truncated] = self._next_id
            self._int_to_atc[self._next_id] = truncated
            self._next_id += 1
        return self._atc_to_int[truncated]

    def decode_int(self, item_id: int) -> str:
        """Decode an integer ID back to its ATC code."""
        if item_id not in self._int_to_atc:
            raise KeyError(f"Unknown item ID: {item_id}")
        return self._int_to_atc[item_id]

    def decode_itemset(self, itemset: Tuple[int, ...]) -> List[str]:
        """Decode an integer itemset to ATC codes."""
        return [self.decode_int(i) for i in itemset]

    def convert_transactions(
        self, transactions: List[List[str]]
    ) -> List[List[List[int]]]:
        """
        Convert ATC-coded transactions to integer-coded basket format.

        Each transaction becomes a single-basket transaction (no sub-baskets),
        compatible with apriori_window_basket.py's read format.

        Args:
            transactions: List of transactions, each a list of ATC codes

        Returns:
            List of transactions in basket format: [[[int, ...]], ...]
        """
        result: List[List[List[int]]] = []
        for txn in transactions:
            items = sorted(set(self.encode_atc(atc) for atc in txn))
            result.append([items])  # Single basket per transaction
        return result

    def get_mapping(self) -> Dict[str, int]:
        """Return current ATC-to-integer mapping."""
        return dict(self._atc_to_int)

    def get_reverse_mapping(self) -> Dict[int, str]:
        """Return current integer-to-ATC mapping."""
        return dict(self._int_to_atc)

    def save_mapping(self, path: str) -> None:
        """Save ATC mapping to JSON file."""
        mapping = {
            "atc_level": self.atc_level,
            "atc_to_int": self._atc_to_int,
            "int_to_atc": {str(k): v for k, v in self._int_to_atc.items()},
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)

    def load_mapping(self, path: str) -> None:
        """Load ATC mapping from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        self.atc_level = mapping["atc_level"]
        self._atc_to_int = mapping["atc_to_int"]
        self._int_to_atc = {int(k): v for k, v in mapping["int_to_atc"].items()}
        self._next_id = max(self._int_to_atc.keys()) + 1 if self._int_to_atc else 1


def write_basket_file(
    transactions: List[List[List[int]]], output_path: str
) -> None:
    """
    Write integer-coded transactions in basket format.

    Format: One transaction per line, items space-separated.
    Single basket per transaction (no '|' separator needed).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for txn in transactions:
            # Flatten single-basket transaction
            items = txn[0] if txn else []
            f.write(" ".join(str(item) for item in items) + "\n")


def is_valid_atc(code: str) -> bool:
    """Check if a string is a valid ATC code pattern."""
    pattern = r"^[A-Z]\d{2}[A-Z]{0,2}\d{0,2}$"
    return bool(re.match(pattern, code.upper()))
