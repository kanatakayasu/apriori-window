"""
Alarm type conversion and transaction generation adapter for manufacturing.

Converts alarm log data (alarm_type, timestamp) into integer-coded
transactions compatible with apriori_window_basket.py.

Domain mapping:
  - Alarm type -> Item (integer-coded)
  - Time bin   -> Transaction
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# SECOM-style alarm type catalog
# ---------------------------------------------------------------------------

ALARM_CATALOG = {
    # Equipment group -> alarm types
    "ETCH": [
        "ETCH_TEMP_HIGH", "ETCH_TEMP_LOW", "ETCH_PRESSURE",
        "ETCH_GAS_FLOW", "ETCH_RF_POWER", "ETCH_ENDPOINT",
    ],
    "CVD": [
        "CVD_TEMP_HIGH", "CVD_TEMP_LOW", "CVD_PRESSURE",
        "CVD_GAS_FLOW", "CVD_DEPOSITION_RATE", "CVD_THICKNESS",
    ],
    "LITHO": [
        "LITHO_ALIGNMENT", "LITHO_FOCUS", "LITHO_EXPOSURE",
        "LITHO_OVERLAY", "LITHO_DEVELOP",
    ],
    "CMP": [
        "CMP_PRESSURE", "CMP_SPEED", "CMP_SLURRY",
        "CMP_ENDPOINT", "CMP_UNIFORMITY",
    ],
    "IMPLANT": [
        "IMPLANT_ENERGY", "IMPLANT_DOSE", "IMPLANT_BEAM",
        "IMPLANT_VACUUM", "IMPLANT_WAFER_TEMP",
    ],
    "INSPECT": [
        "INSPECT_DEFECT_COUNT", "INSPECT_PARTICLE",
        "INSPECT_SCRATCH", "INSPECT_PATTERN",
    ],
    "GENERAL": [
        "SENSOR_DRIFT", "VIBRATION_HIGH", "POWER_FLUCTUATION",
        "COOLING_FAULT", "INTERLOCK_TRIP",
    ],
}


def get_all_alarm_types() -> List[str]:
    """Get flat list of all alarm types across equipment groups."""
    result = []
    for group_alarms in ALARM_CATALOG.values():
        result.extend(group_alarms)
    return result


def get_equipment_group(alarm_type: str) -> Optional[str]:
    """Return equipment group for a given alarm type."""
    for group, alarms in ALARM_CATALOG.items():
        if alarm_type in alarms:
            return group
    return None


class AlarmAdapter:
    """
    Adapter for converting alarm log data into integer transactions
    for dense interval mining.
    """

    def __init__(self, time_bin_seconds: int = 3600):
        """
        Args:
            time_bin_seconds: Time bin width in seconds for transaction
                              generation. Default: 3600 (1 hour).
        """
        if time_bin_seconds < 1:
            raise ValueError(f"time_bin_seconds must be >= 1, got {time_bin_seconds}")
        self.time_bin_seconds = time_bin_seconds
        self._alarm_to_int: Dict[str, int] = {}
        self._int_to_alarm: Dict[int, str] = {}
        self._next_id: int = 1

    def encode_alarm(self, alarm_type: str) -> int:
        """Encode an alarm type string to an integer ID."""
        if alarm_type not in self._alarm_to_int:
            self._alarm_to_int[alarm_type] = self._next_id
            self._int_to_alarm[self._next_id] = alarm_type
            self._next_id += 1
        return self._alarm_to_int[alarm_type]

    def decode_alarm(self, alarm_id: int) -> str:
        """Decode an integer ID back to alarm type string."""
        if alarm_id not in self._int_to_alarm:
            raise KeyError(f"Unknown alarm ID: {alarm_id}")
        return self._int_to_alarm[alarm_id]

    def decode_pattern(self, pattern: Tuple[int, ...]) -> Tuple[str, ...]:
        """Decode a pattern (tuple of int IDs) to alarm type names."""
        return tuple(self.decode_alarm(a) for a in pattern)

    def get_equipment_groups(self, pattern: Tuple[int, ...]) -> List[str]:
        """Get equipment groups for a pattern."""
        groups = set()
        for alarm_id in pattern:
            alarm_type = self.decode_alarm(alarm_id)
            group = get_equipment_group(alarm_type)
            if group:
                groups.add(group)
        return sorted(groups)

    def alarm_log_to_transactions(
        self,
        alarm_log: List[Tuple[str, int]],
    ) -> Tuple[List[List[List[int]]], int]:
        """
        Convert alarm log entries to basket-format transactions.

        Args:
            alarm_log: List of (alarm_type, timestamp_seconds) tuples,
                       sorted by timestamp.

        Returns:
            (transactions, n_bins):
                transactions: List[List[List[int]]] in basket format
                    (1 basket per transaction for manufacturing)
                n_bins: Total number of time bins
        """
        if not alarm_log:
            return [], 0

        # Find time range
        min_time = alarm_log[0][1]
        max_time = alarm_log[-1][1]
        n_bins = (max_time - min_time) // self.time_bin_seconds + 1

        # Bin alarms into transactions
        bins: Dict[int, List[int]] = {}
        for alarm_type, timestamp in alarm_log:
            bin_idx = (timestamp - min_time) // self.time_bin_seconds
            alarm_id = self.encode_alarm(alarm_type)
            bins.setdefault(bin_idx, []).append(alarm_id)

        # Create transaction list (empty bins = empty transactions)
        transactions: List[List[List[int]]] = []
        for t in range(n_bins):
            if t in bins:
                # Deduplicate within bin, single basket per transaction
                items = sorted(set(bins[t]))
                transactions.append([items])
            else:
                transactions.append([])

        return transactions, n_bins

    def save_mapping(self, path: str) -> None:
        """Save alarm-to-integer mapping as JSON."""
        mapping = {
            "alarm_to_int": self._alarm_to_int,
            "int_to_alarm": {str(k): v for k, v in self._int_to_alarm.items()},
            "time_bin_seconds": self.time_bin_seconds,
        }
        Path(path).write_text(json.dumps(mapping, indent=2, ensure_ascii=False))

    def load_mapping(self, path: str) -> None:
        """Load alarm-to-integer mapping from JSON."""
        data = json.loads(Path(path).read_text())
        self._alarm_to_int = data["alarm_to_int"]
        self._int_to_alarm = {int(k): v for k, v in data["int_to_alarm"].items()}
        self._next_id = max(self._int_to_alarm.keys()) + 1 if self._int_to_alarm else 1
        self.time_bin_seconds = data.get("time_bin_seconds", 3600)
