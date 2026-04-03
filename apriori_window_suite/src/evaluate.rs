//! Evaluation metrics for Event Attribution experiments.
//!
//! Port of `experiments/src/evaluate.py` to Rust.
//!
//! Computes Precision, Recall, F1 against known ground truth,
//! and False Attribution Rate for Type B (unrelated) patterns.

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// A predicted (pattern, event_name) attribution from the pipeline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictedAttribution {
    /// Sorted item IDs in the predicted pattern.
    pub pattern: Vec<i64>,
    /// Event name (will be mapped to event_id via events.json).
    pub event_name: String,
}

/// Precision / Recall / F1 evaluation result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvalResult {
    pub precision: f64,
    pub recall: f64,
    pub f1: f64,
    pub tp: usize,
    pub fp: usize,
    pub fn_count: usize,
}

/// False Attribution Rate evaluation result for Type B patterns.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FalseAttributionResult {
    pub false_attribution_rate: f64,
    pub n_falsely_attributed: usize,
    pub n_unrelated: usize,
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Normalize a pattern to a sorted vector for comparison.
fn pattern_key(pattern: &[i64]) -> Vec<i64> {
    let mut sorted = pattern.to_vec();
    sorted.sort();
    sorted
}

/// Ground-truth entry loaded from JSON.
#[derive(Debug, Deserialize)]
struct GtEntry {
    pattern: Vec<i64>,
    event_id: String,
}

/// Event entry loaded from events.json.
#[derive(Debug, Deserialize)]
struct EventEntry {
    #[allow(dead_code)]
    event_id: String,
    name: String,
}

/// Unrelated pattern entry loaded from JSON.
#[derive(Debug, Deserialize)]
struct UnrelatedEntry {
    pattern: Vec<i64>,
}

// ---------------------------------------------------------------------------
// Evaluation functions
// ---------------------------------------------------------------------------

/// Evaluate attribution results against ground truth, mapping event names
/// to event IDs using the events file.
///
/// A predicted `(pattern, event_id)` is a true positive if there exists a
/// ground-truth entry with the same `event_id` AND the ground-truth pattern
/// is equal to (as a set) the predicted pattern.
///
/// # Panics
///
/// Panics if the ground-truth or events file cannot be read or parsed.
pub fn evaluate_with_event_name_mapping(
    predicted: &[PredictedAttribution],
    gt_path: &str,
    events_path: &str,
) -> EvalResult {
    // Load ground truth
    let gt_text = fs::read_to_string(gt_path)
        .unwrap_or_else(|_| panic!("failed to read ground truth file: {gt_path}"));
    let gt_raw: Vec<GtEntry> =
        serde_json::from_str(&gt_text).expect("failed to parse ground truth JSON");

    // Load events to build name → event_id mapping
    let events_text = fs::read_to_string(events_path)
        .unwrap_or_else(|_| panic!("failed to read events file: {events_path}"));
    let events_raw: Vec<serde_json::Value> =
        serde_json::from_str(&events_text).expect("failed to parse events JSON");

    let mut name_to_id = std::collections::HashMap::new();
    for entry in &events_raw {
        let name = entry["name"].as_str().unwrap_or("").to_string();
        let eid = entry["event_id"].as_str().unwrap_or("").to_string();
        name_to_id.insert(name, eid);
    }

    // Build ground truth set: (pattern_key, event_id)
    let gt_set: HashSet<(Vec<i64>, String)> = gt_raw
        .iter()
        .map(|entry| (pattern_key(&entry.pattern), entry.event_id.clone()))
        .collect();

    // Build predicted set: map event_name → event_id, then (pattern_key, event_id)
    let pred_set: HashSet<(Vec<i64>, String)> = predicted
        .iter()
        .map(|p| {
            let pk = pattern_key(&p.pattern);
            let eid = name_to_id
                .get(&p.event_name)
                .cloned()
                .unwrap_or_else(|| p.event_name.clone());
            (pk, eid)
        })
        .collect();

    let tp_set: HashSet<_> = gt_set.intersection(&pred_set).collect();
    let fp_set: HashSet<_> = pred_set.difference(&gt_set).collect();
    let fn_set: HashSet<_> = gt_set.difference(&pred_set).collect();

    let tp = tp_set.len();
    let fp = fp_set.len();
    let fn_count = fn_set.len();

    let precision = if tp + fp > 0 {
        tp as f64 / (tp + fp) as f64
    } else {
        0.0
    };
    let recall = if tp + fn_count > 0 {
        tp as f64 / (tp + fn_count) as f64
    } else {
        0.0
    };
    let f1 = if precision + recall > 0.0 {
        2.0 * precision * recall / (precision + recall)
    } else {
        0.0
    };

    EvalResult {
        precision,
        recall,
        f1,
        tp,
        fp,
        fn_count,
    }
}

/// Evaluate False Attribution Rate for Type B (unrelated) patterns.
///
/// For each unrelated pattern, checks if any predicted attribution's pattern
/// (as a set) matches the unrelated pattern exactly. FAR = n_falsely_attributed / n_unrelated.
///
/// # Panics
///
/// Panics if the unrelated or events file cannot be read or parsed.
pub fn evaluate_false_attribution_rate(
    predicted: &[PredictedAttribution],
    unrelated_path: &str,
    events_path: &str,
) -> FalseAttributionResult {
    // Load unrelated patterns
    let unrelated_text = fs::read_to_string(unrelated_path)
        .unwrap_or_else(|_| panic!("failed to read unrelated patterns file: {unrelated_path}"));
    let unrelated_raw: Vec<UnrelatedEntry> =
        serde_json::from_str(&unrelated_text).expect("failed to parse unrelated patterns JSON");

    // Load events for name → id mapping
    let events_text = fs::read_to_string(events_path)
        .unwrap_or_else(|_| panic!("failed to read events file: {events_path}"));
    let events_raw: Vec<serde_json::Value> =
        serde_json::from_str(&events_text).expect("failed to parse events JSON");

    let mut name_to_id = std::collections::HashMap::new();
    for entry in &events_raw {
        let name = entry["name"].as_str().unwrap_or("").to_string();
        let eid = entry["event_id"].as_str().unwrap_or("").to_string();
        name_to_id.insert(name, eid);
    }

    // Build set of unrelated pattern keys
    let unrelated_set: HashSet<Vec<i64>> = unrelated_raw
        .iter()
        .map(|entry| pattern_key(&entry.pattern))
        .collect();

    let n_unrelated = unrelated_set.len();

    // Check each prediction: does its pattern match any unrelated pattern?
    let mut falsely_attributed_patterns: HashSet<Vec<i64>> = HashSet::new();
    let mut seen: HashSet<(Vec<i64>, String)> = HashSet::new();

    for p in predicted {
        let pk = pattern_key(&p.pattern);
        let eid = name_to_id
            .get(&p.event_name)
            .cloned()
            .unwrap_or_else(|| p.event_name.clone());

        if unrelated_set.contains(&pk) {
            let key = (pk.clone(), eid);
            if seen.insert(key) {
                falsely_attributed_patterns.insert(pk);
            }
        }
    }

    let n_falsely = falsely_attributed_patterns.len();
    let rate = n_falsely as f64 / n_unrelated.max(1) as f64;

    FalseAttributionResult {
        false_attribution_rate: rate,
        n_falsely_attributed: n_falsely,
        n_unrelated,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn write_json(dir: &TempDir, name: &str, content: &str) -> String {
        let path = dir.path().join(name);
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(content.as_bytes()).unwrap();
        path.to_string_lossy().to_string()
    }

    #[test]
    fn test_evaluate_perfect_match() {
        let tmp = TempDir::new().unwrap();

        let gt = r#"[
            {"pattern": [5, 15], "event_id": "E1"},
            {"pattern": [25, 35], "event_id": "E2"}
        ]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200},
            {"event_id": "E2", "name": "Event_2", "start": 300, "end": 400}
        ]"#;

        let gt_path = write_json(&tmp, "gt.json", gt);
        let events_path = write_json(&tmp, "events.json", events);

        let predicted = vec![
            PredictedAttribution {
                pattern: vec![5, 15],
                event_name: "Event_1".into(),
            },
            PredictedAttribution {
                pattern: vec![25, 35],
                event_name: "Event_2".into(),
            },
        ];

        let result = evaluate_with_event_name_mapping(&predicted, &gt_path, &events_path);
        assert_eq!(result.tp, 2);
        assert_eq!(result.fp, 0);
        assert_eq!(result.fn_count, 0);
        assert!((result.precision - 1.0).abs() < 1e-10);
        assert!((result.recall - 1.0).abs() < 1e-10);
        assert!((result.f1 - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_evaluate_partial_match() {
        let tmp = TempDir::new().unwrap();

        let gt = r#"[
            {"pattern": [5, 15], "event_id": "E1"},
            {"pattern": [25, 35], "event_id": "E2"}
        ]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200},
            {"event_id": "E2", "name": "Event_2", "start": 300, "end": 400}
        ]"#;

        let gt_path = write_json(&tmp, "gt.json", gt);
        let events_path = write_json(&tmp, "events.json", events);

        // Only predict one correctly, miss the other
        let predicted = vec![PredictedAttribution {
            pattern: vec![5, 15],
            event_name: "Event_1".into(),
        }];

        let result = evaluate_with_event_name_mapping(&predicted, &gt_path, &events_path);
        assert_eq!(result.tp, 1);
        assert_eq!(result.fp, 0);
        assert_eq!(result.fn_count, 1);
        assert!((result.precision - 1.0).abs() < 1e-10);
        assert!((result.recall - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_evaluate_with_false_positive() {
        let tmp = TempDir::new().unwrap();

        let gt = r#"[{"pattern": [5, 15], "event_id": "E1"}]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200},
            {"event_id": "D1", "name": "Decoy_1", "start": 300, "end": 400}
        ]"#;

        let gt_path = write_json(&tmp, "gt.json", gt);
        let events_path = write_json(&tmp, "events.json", events);

        let predicted = vec![
            PredictedAttribution {
                pattern: vec![5, 15],
                event_name: "Event_1".into(),
            },
            PredictedAttribution {
                pattern: vec![99, 100],
                event_name: "Decoy_1".into(),
            },
        ];

        let result = evaluate_with_event_name_mapping(&predicted, &gt_path, &events_path);
        assert_eq!(result.tp, 1);
        assert_eq!(result.fp, 1);
        assert_eq!(result.fn_count, 0);
        assert!((result.precision - 0.5).abs() < 1e-10);
        assert!((result.recall - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_evaluate_empty_predictions() {
        let tmp = TempDir::new().unwrap();

        let gt = r#"[{"pattern": [5, 15], "event_id": "E1"}]"#;
        let events = r#"[{"event_id": "E1", "name": "Event_1", "start": 100, "end": 200}]"#;

        let gt_path = write_json(&tmp, "gt.json", gt);
        let events_path = write_json(&tmp, "events.json", events);

        let predicted: Vec<PredictedAttribution> = vec![];
        let result = evaluate_with_event_name_mapping(&predicted, &gt_path, &events_path);
        assert_eq!(result.tp, 0);
        assert_eq!(result.fp, 0);
        assert_eq!(result.fn_count, 1);
        assert!((result.precision - 0.0).abs() < 1e-10);
        assert!((result.recall - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_false_attribution_rate_none_falsely_attributed() {
        let tmp = TempDir::new().unwrap();

        let unrelated = r#"[{"pattern": [65, 75]}, {"pattern": [85, 95]}]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200}
        ]"#;

        let unrelated_path = write_json(&tmp, "unrelated.json", unrelated);
        let events_path = write_json(&tmp, "events.json", events);

        // Predictions don't match any unrelated pattern
        let predicted = vec![PredictedAttribution {
            pattern: vec![5, 15],
            event_name: "Event_1".into(),
        }];

        let result =
            evaluate_false_attribution_rate(&predicted, &unrelated_path, &events_path);
        assert_eq!(result.n_unrelated, 2);
        assert_eq!(result.n_falsely_attributed, 0);
        assert!((result.false_attribution_rate - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_false_attribution_rate_one_falsely_attributed() {
        let tmp = TempDir::new().unwrap();

        let unrelated = r#"[{"pattern": [65, 75]}, {"pattern": [85, 95]}]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200}
        ]"#;

        let unrelated_path = write_json(&tmp, "unrelated.json", unrelated);
        let events_path = write_json(&tmp, "events.json", events);

        // One prediction matches an unrelated pattern
        let predicted = vec![
            PredictedAttribution {
                pattern: vec![5, 15],
                event_name: "Event_1".into(),
            },
            PredictedAttribution {
                pattern: vec![65, 75],
                event_name: "Event_1".into(),
            },
        ];

        let result =
            evaluate_false_attribution_rate(&predicted, &unrelated_path, &events_path);
        assert_eq!(result.n_unrelated, 2);
        assert_eq!(result.n_falsely_attributed, 1);
        assert!((result.false_attribution_rate - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_false_attribution_rate_all_falsely_attributed() {
        let tmp = TempDir::new().unwrap();

        let unrelated = r#"[{"pattern": [65, 75]}, {"pattern": [85, 95]}]"#;
        let events = r#"[
            {"event_id": "E1", "name": "Event_1", "start": 100, "end": 200}
        ]"#;

        let unrelated_path = write_json(&tmp, "unrelated.json", unrelated);
        let events_path = write_json(&tmp, "events.json", events);

        let predicted = vec![
            PredictedAttribution {
                pattern: vec![65, 75],
                event_name: "Event_1".into(),
            },
            PredictedAttribution {
                pattern: vec![85, 95],
                event_name: "Event_1".into(),
            },
        ];

        let result =
            evaluate_false_attribution_rate(&predicted, &unrelated_path, &events_path);
        assert_eq!(result.n_unrelated, 2);
        assert_eq!(result.n_falsely_attributed, 2);
        assert!((result.false_attribution_rate - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_pattern_key_sorts() {
        assert_eq!(pattern_key(&[15, 5]), vec![5, 15]);
        assert_eq!(pattern_key(&[35, 25, 5]), vec![5, 25, 35]);
    }
}
