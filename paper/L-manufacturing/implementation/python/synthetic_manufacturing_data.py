"""
Synthetic manufacturing alarm data generator.

Generates SECOM-like alarm data with:
- Multiple equipment groups (ETCH, CVD, LITHO, CMP, IMPLANT, INSPECT, GENERAL)
- Configurable fault injection (alarm bursts at specific time regions)
- Maintenance events that resolve or introduce fault patterns
- Ground truth annotations for evaluation
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from alarm_adapter import ALARM_CATALOG, get_all_alarm_types, AlarmAdapter
from maintenance_contrast import MaintenanceEvent


@dataclass
class FaultScenario:
    """A fault scenario to inject into synthetic data."""
    fault_id: str
    alarm_types: List[str]  # alarms triggered by this fault
    start_bin: int           # fault active from this bin
    end_bin: int             # fault active until this bin
    burst_prob: float        # probability of alarm per bin during fault
    description: str = ""


@dataclass
class SyntheticManufacturingConfig:
    """Configuration for synthetic data generation."""
    n_time_bins: int = 2000
    seed: int = 42
    base_alarm_prob: float = 0.03   # background alarm probability
    n_equipment_groups: int = 7     # how many equipment groups to include
    fault_scenarios: List[FaultScenario] = field(default_factory=list)
    maintenance_events: List[MaintenanceEvent] = field(default_factory=list)


def create_default_config() -> SyntheticManufacturingConfig:
    """Create a default configuration with realistic fault scenarios."""
    config = SyntheticManufacturingConfig(
        n_time_bins=2000,
        seed=42,
        base_alarm_prob=0.03,
    )

    # Fault F1: Etch chamber degradation (bins 200-500, resolved by maintenance at 500)
    config.fault_scenarios.append(FaultScenario(
        fault_id="F1",
        alarm_types=["ETCH_TEMP_HIGH", "ETCH_PRESSURE", "ETCH_RF_POWER"],
        start_bin=200,
        end_bin=500,
        burst_prob=0.55,
        description="Etch chamber degradation causing thermal + pressure alarms",
    ))

    # Fault F2: CVD process drift (bins 600-900, resolved by calibration at 900)
    config.fault_scenarios.append(FaultScenario(
        fault_id="F2",
        alarm_types=["CVD_TEMP_HIGH", "CVD_DEPOSITION_RATE", "CVD_THICKNESS"],
        start_bin=600,
        end_bin=900,
        burst_prob=0.50,
        description="CVD process drift causing deposition anomalies",
    ))

    # Fault F3: Cross-equipment vibration (bins 300-700)
    config.fault_scenarios.append(FaultScenario(
        fault_id="F3",
        alarm_types=["VIBRATION_HIGH", "CMP_UNIFORMITY", "LITHO_ALIGNMENT"],
        start_bin=300,
        end_bin=700,
        burst_prob=0.40,
        description="Facility vibration affecting CMP and lithography",
    ))

    # Fault F4: Introduced by recipe update (bins 1200-1600)
    config.fault_scenarios.append(FaultScenario(
        fault_id="F4",
        alarm_types=["IMPLANT_ENERGY", "IMPLANT_DOSE", "IMPLANT_BEAM"],
        start_bin=1200,
        end_bin=1600,
        burst_prob=0.50,
        description="Implant recipe change introducing beam instability",
    ))

    # Fault F5: Inspection false positives (bins 1400-1800)
    config.fault_scenarios.append(FaultScenario(
        fault_id="F5",
        alarm_types=["INSPECT_DEFECT_COUNT", "INSPECT_PARTICLE", "SENSOR_DRIFT"],
        start_bin=1400,
        end_bin=1800,
        burst_prob=0.45,
        description="Sensor drift causing inspection false positives",
    ))

    # Maintenance events
    config.maintenance_events = [
        MaintenanceEvent(
            event_id="M1",
            timestamp=500,
            event_type="scheduled_maintenance",
            equipment_group="ETCH",
            description="Etch chamber PM - resolved F1",
        ),
        MaintenanceEvent(
            event_id="M2",
            timestamp=700,
            event_type="part_replacement",
            equipment_group="GENERAL",
            description="Vibration dampener replacement",
        ),
        MaintenanceEvent(
            event_id="M3",
            timestamp=900,
            event_type="calibration",
            equipment_group="CVD",
            description="CVD temperature recalibration - resolved F2",
        ),
        MaintenanceEvent(
            event_id="M4",
            timestamp=1200,
            event_type="recipe_update",
            equipment_group="IMPLANT",
            description="Implant recipe update - introduced F4",
        ),
        MaintenanceEvent(
            event_id="M5",
            timestamp=1800,
            event_type="calibration",
            equipment_group="INSPECT",
            description="Sensor recalibration - resolved F5",
        ),
    ]

    return config


def generate_synthetic_alarms(
    config: SyntheticManufacturingConfig,
) -> Tuple[List[Tuple[str, int]], Dict[str, FaultScenario]]:
    """
    Generate synthetic alarm log data.

    Returns:
        (alarm_log, ground_truth):
            alarm_log: List of (alarm_type, time_bin) sorted by time
            ground_truth: Dict of fault_id -> FaultScenario
    """
    rng = random.Random(config.seed)
    all_alarm_types = get_all_alarm_types()
    alarm_log: List[Tuple[str, int]] = []

    # Background alarms
    for t in range(config.n_time_bins):
        for alarm_type in all_alarm_types:
            if rng.random() < config.base_alarm_prob:
                alarm_log.append((alarm_type, t))

    # Fault injection
    for fault in config.fault_scenarios:
        for t in range(fault.start_bin, fault.end_bin):
            for alarm_type in fault.alarm_types:
                if rng.random() < fault.burst_prob:
                    alarm_log.append((alarm_type, t))

    # Sort by time
    alarm_log.sort(key=lambda x: (x[1], x[0]))

    ground_truth = {f.fault_id: f for f in config.fault_scenarios}

    return alarm_log, ground_truth


def generate_transactions(
    config: Optional[SyntheticManufacturingConfig] = None,
) -> Tuple[List[List[List[int]]], AlarmAdapter, List[MaintenanceEvent], Dict[str, FaultScenario]]:
    """
    Generate synthetic data and convert to transactions.

    Returns:
        (transactions, adapter, events, ground_truth)
    """
    if config is None:
        config = create_default_config()

    alarm_log, ground_truth = generate_synthetic_alarms(config)
    adapter = AlarmAdapter(time_bin_seconds=1)  # bins already integer
    transactions, n_bins = adapter.alarm_log_to_transactions(alarm_log)

    # Pad to n_time_bins if needed
    while len(transactions) < config.n_time_bins:
        transactions.append([])

    return transactions, adapter, config.maintenance_events, ground_truth
