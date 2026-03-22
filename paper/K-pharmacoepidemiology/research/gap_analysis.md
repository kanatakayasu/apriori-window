# Gap Analysis: Dense Prescription Patterns and Regulatory Event Attribution

## Research Gaps

### Gap 1: No Dense Interval Detection for Co-Prescription Patterns
**Current State**: Existing pharmacovigilance methods (PRR, ROR, BCPNN, GPS) operate on aggregate counts across the entire observation period. ITS divides time into fixed segments around a known intervention point. Sequential pattern mining discovers ordered sequences but not temporal density variations.

**Missing**: A method that automatically identifies **time intervals** where specific drug combination co-prescriptions become **unusually frequent** (dense), without requiring pre-specified time points.

**Our Solution**: Apply the sliding-window dense interval detection from apriori_window to prescription transaction data, treating each patient visit as a transaction and ATC-coded medications as items.

### Gap 2: Automated Regulatory Event Attribution
**Current State**: ITS analysis requires the analyst to manually specify the intervention time point. SCCS requires pre-specified exposure windows. There is no automated method that takes a set of regulatory events and a set of detected pattern changes and performs systematic attribution.

**Missing**: An automated pipeline that:
1. Detects change points in prescription pattern density
2. Matches them to known regulatory events (FDA safety communications, drug withdrawals, label changes)
3. Quantifies statistical significance of the association

**Our Solution**: Adapt the event attribution framework from the core apriori_window methodology to link dense interval boundaries (pattern emergence/disappearance) to regulatory event timestamps.

### Gap 3: Multi-Pattern Contrast Analysis
**Current State**: Traditional pharmacovigilance analyzes one drug-event pair at a time. Association rule mining finds static patterns. No framework systematically examines which co-prescription patterns appear, disappear, or shift in composition around a regulatory event.

**Missing**: A contrast pattern framework that simultaneously detects:
- Patterns that **disappear** after a safety alert (expected: targeted drug combinations decline)
- Patterns that **emerge** after a safety alert (compensatory: alternative drug combinations increase)
- Patterns that remain **unchanged** (controls: unaffected drug classes)

**Our Solution**: Define pre-event and post-event windows around each regulatory event. Compare dense intervals and support levels between periods to identify contrast patterns with statistical significance testing.

### Gap 4: Sliding Window Granularity for Prescription Monitoring
**Current State**: Fixed time bins (monthly, quarterly) are standard in drug utilization studies. This loses temporal resolution and can miss short-lived prescription surges or gradual transitions.

**Missing**: Fine-grained temporal analysis using sliding windows that can detect both abrupt and gradual changes in prescription patterns.

**Our Solution**: The apriori_window sliding window approach provides transaction-level granularity while maintaining computational efficiency through Apriori pruning.

## Positioning Matrix

| Method | Temporal | Multi-drug | Auto-attribution | Dense intervals |
|--------|----------|------------|-----------------|-----------------|
| PRR/ROR | No | No | No | No |
| BCPNN/GPS | No | No | No | No |
| SCCS | Yes | No | No | No |
| ITS | Yes | No | Manual | No |
| Apriori ARM | No | Yes | No | No |
| CSPADE | Yes (order) | Yes | No | No |
| TPD | Yes | No | No | Partial |
| **Ours** | **Yes** | **Yes** | **Yes** | **Yes** |

## Target Venue Fit
- **JAMIA (Journal of the American Medical Informatics Association)**: Strong fit—methods paper with clinical informatics application. Emphasis on EHR data, automated analysis, reproducibility.
- **AMIA Annual Symposium**: Alternative venue—shorter format, strong clinical informatics community.
- Both venues value: methodological novelty, clinical relevance, reproducibility, and practical utility.
