//! Synthetic data generation for Event Attribution experiments.
//!
//! Port of `experiments/src/gen_synthetic.py` to Rust.
//!
//! Generates:
//!   1. Transaction file (single-basket format)
//!   2. Events JSON file
//!   3. Ground truth JSON (pattern → event_id pairs)
//!   4. Unrelated patterns JSON (for FAR evaluation)

use rand::prelude::*;
use rand::rngs::StdRng;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

// ---------------------------------------------------------------------------
// Config types
// ---------------------------------------------------------------------------

/// Planted signal: vocabulary-internal boost (Type A).
///
/// Items from the base vocabulary that have boosted co-occurrence probability
/// during the associated event window.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlantedPattern {
    /// Items in the pattern (from base vocabulary).
    pub items: Vec<i64>,
    /// Index into `SyntheticConfig::events` identifying the associated event.
    pub event_idx: usize,
    /// Probability of simultaneous insertion during event window.
    pub boost_factor: f64,
    /// Baseline probability for each item outside event window (0 = no baseline).
    #[serde(default)]
    pub baseline_prob: f64,
}

/// Unrelated dense pattern (Type B).
///
/// Dense pattern NOT associated with any event. Used to test false-attribution
/// rejection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnrelatedPattern {
    pub items: Vec<i64>,
    /// When the dense period begins (transaction index).
    pub active_start: i64,
    /// When the dense period ends (transaction index, inclusive).
    pub active_end: i64,
    /// Probability of simultaneous insertion during active period.
    pub boost_factor: f64,
}

/// Synthetic event definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticEvent {
    pub name: String,
    pub start: i64,
    pub end: i64,
}

/// Correlated item pair: if item_a appears, item_b also appears with given probability.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorrelatedPair {
    pub item_a: i64,
    pub item_b: i64,
    pub corr_prob: f64,
}

/// Configuration for synthetic data generation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticConfig {
    /// Number of distinct items in the vocabulary.
    pub n_items: usize,
    /// Number of transactions to generate.
    pub n_transactions: usize,
    /// Per-item base occurrence probabilities (length `n_items`, index 0 → item 1).
    /// If empty, all items use `p_base`.
    pub item_probs: Vec<f64>,
    /// Uniform base probability (used when `item_probs` is empty).
    pub p_base: f64,
    /// Type A planted signals.
    pub planted_patterns: Vec<PlantedPattern>,
    /// Type B unrelated dense patterns.
    pub unrelated_patterns: Vec<UnrelatedPattern>,
    /// Real events (one per planted signal, referenced by `event_idx`).
    pub events: Vec<SyntheticEvent>,
    /// Type C decoy events (no associated pattern changes).
    pub decoy_events: Vec<SyntheticEvent>,
    /// Correlated item pairs (optional).
    #[serde(default)]
    pub correlated_pairs: Vec<CorrelatedPair>,
    /// RNG seed for reproducibility.
    pub seed: u64,
}

/// Paths and metadata returned by `generate_synthetic`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticInfo {
    pub txn_path: String,
    pub events_path: String,
    pub gt_path: String,
    pub unrelated_path: Option<String>,
}

// ---------------------------------------------------------------------------
// Config scaling
// ---------------------------------------------------------------------------

/// Scale a SyntheticConfig's time positions proportionally to a new N.
///
/// All position-dependent fields (event start/end, unrelated pattern
/// active_start/active_end, decoy event start/end) are multiplied by
/// `new_n / original_n`. Use this when you want to run the same experiment
/// design at a different transaction scale.
pub fn scale_config_to_n(config: &SyntheticConfig, new_n: usize) -> SyntheticConfig {
    let orig_n = config.n_transactions as i64;
    let scale = new_n as f64 / orig_n as f64;

    let events = config
        .events
        .iter()
        .map(|e| SyntheticEvent {
            name: e.name.clone(),
            start: (e.start as f64 * scale).round() as i64,
            end: (e.end as f64 * scale).round() as i64,
        })
        .collect();

    let decoy_events = config
        .decoy_events
        .iter()
        .map(|e| SyntheticEvent {
            name: e.name.clone(),
            start: (e.start as f64 * scale).round() as i64,
            end: (e.end as f64 * scale).round() as i64,
        })
        .collect();

    let unrelated_patterns = config
        .unrelated_patterns
        .iter()
        .map(|u| UnrelatedPattern {
            items: u.items.clone(),
            active_start: (u.active_start as f64 * scale).round() as i64,
            active_end: (u.active_end as f64 * scale).round() as i64,
            boost_factor: u.boost_factor,
        })
        .collect();

    SyntheticConfig {
        n_items: config.n_items,
        n_transactions: new_n,
        item_probs: config.item_probs.clone(),
        p_base: config.p_base,
        planted_patterns: config.planted_patterns.clone(),
        unrelated_patterns,
        events,
        decoy_events,
        correlated_pairs: config.correlated_pairs.clone(),
        seed: config.seed,
    }
}

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------

/// Generate a synthetic dataset and write to `out_dir`.
///
/// Produces:
///   - `transactions.txt` — one transaction per line, space-separated item IDs
///   - `events.json` — array of `{event_id, name, start, end}`
///   - `ground_truth.json` — array of `{pattern, event_id}`
///   - `unrelated_patterns.json` — array of `{pattern, active_start, active_end, boost_factor}`
pub fn generate_synthetic(config: &SyntheticConfig, out_dir: &str) -> SyntheticInfo {
    let out = Path::new(out_dir);
    fs::create_dir_all(out).expect("failed to create output directory");

    let mut rng = StdRng::seed_from_u64(config.seed);
    let mut transactions: Vec<Vec<i64>> = Vec::with_capacity(config.n_transactions);

    let use_item_probs = !config.item_probs.is_empty();

    for t in 0..config.n_transactions {
        let t_i64 = t as i64;
        let mut items = BTreeSet::new();

        // Baseline item occurrence
        for item_idx in 0..config.n_items {
            let p = if use_item_probs {
                config.item_probs[item_idx]
            } else {
                config.p_base
            };
            if rng.gen::<f64>() < p {
                items.insert((item_idx + 1) as i64);
            }
        }

        // Type A: planted signals
        for planted in &config.planted_patterns {
            let event = &config.events[planted.event_idx];
            if event.start <= t_i64 && t_i64 <= event.end {
                // Inside event window: insert all items simultaneously
                if rng.gen::<f64>() < planted.boost_factor.min(1.0) {
                    for &item in &planted.items {
                        items.insert(item);
                    }
                }
            } else if planted.baseline_prob > 0.0 {
                // Outside event window: each item independently
                for &item in &planted.items {
                    if rng.gen::<f64>() < planted.baseline_prob {
                        items.insert(item);
                    }
                }
            }
        }

        // Type B: unrelated dense patterns
        for udp in &config.unrelated_patterns {
            if udp.active_start <= t_i64 && t_i64 <= udp.active_end {
                if rng.gen::<f64>() < udp.boost_factor.min(1.0) {
                    for &item in &udp.items {
                        items.insert(item);
                    }
                }
            }
        }

        // Correlated pairs
        for cp in &config.correlated_pairs {
            if items.contains(&cp.item_a) && rng.gen::<f64>() < cp.corr_prob {
                items.insert(cp.item_b);
            }
        }

        transactions.push(items.into_iter().collect());
    }

    // --- Write transactions ---
    let txn_path = out.join("transactions.txt");
    let txn_content: String = transactions
        .iter()
        .map(|txn| {
            txn.iter()
                .map(|x| x.to_string())
                .collect::<Vec<_>>()
                .join(" ")
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    fs::write(&txn_path, txn_content).expect("failed to write transactions");

    // --- Write events.json ---
    // Combine real events (from planted signals) and decoy events
    let mut events_json: Vec<serde_json::Value> = Vec::new();
    for (i, event) in config.events.iter().enumerate() {
        events_json.push(serde_json::json!({
            "event_id": format!("E{}", i + 1),
            "name": event.name,
            "start": event.start,
            "end": event.end,
        }));
    }
    for (i, decoy) in config.decoy_events.iter().enumerate() {
        events_json.push(serde_json::json!({
            "event_id": format!("D{}", i + 1),
            "name": decoy.name,
            "start": decoy.start,
            "end": decoy.end,
        }));
    }

    let events_path = out.join("events.json");
    let events_str =
        serde_json::to_string_pretty(&events_json).expect("failed to serialize events");
    fs::write(&events_path, events_str).expect("failed to write events");

    // --- Write ground_truth.json ---
    let mut gt_json: Vec<serde_json::Value> = Vec::new();
    for planted in &config.planted_patterns {
        let mut sorted_items = planted.items.clone();
        sorted_items.sort();
        gt_json.push(serde_json::json!({
            "pattern": sorted_items,
            "event_id": format!("E{}", planted.event_idx + 1),
        }));
    }

    let gt_path = out.join("ground_truth.json");
    let gt_str =
        serde_json::to_string_pretty(&gt_json).expect("failed to serialize ground truth");
    fs::write(&gt_path, gt_str).expect("failed to write ground truth");

    // --- Write unrelated_patterns.json ---
    let unrelated_path = if !config.unrelated_patterns.is_empty() {
        let mut unrelated_json: Vec<serde_json::Value> = Vec::new();
        for udp in &config.unrelated_patterns {
            let mut sorted_items = udp.items.clone();
            sorted_items.sort();
            unrelated_json.push(serde_json::json!({
                "pattern": sorted_items,
                "active_start": udp.active_start,
                "active_end": udp.active_end,
                "boost_factor": udp.boost_factor,
            }));
        }
        let upath = out.join("unrelated_patterns.json");
        let ustr = serde_json::to_string_pretty(&unrelated_json)
            .expect("failed to serialize unrelated patterns");
        fs::write(&upath, ustr).expect("failed to write unrelated patterns");
        Some(upath.to_string_lossy().to_string())
    } else {
        None
    };

    SyntheticInfo {
        txn_path: txn_path.to_string_lossy().to_string(),
        events_path: events_path.to_string_lossy().to_string(),
        gt_path: gt_path.to_string_lossy().to_string(),
        unrelated_path,
    }
}

// ---------------------------------------------------------------------------
// Config factory functions
// ---------------------------------------------------------------------------

/// EX1 config: 3 Type A planted signals + Type B unrelated + Type C decoy events.
///
/// Type A items: `[5,15], [25,35], [45,55]` — vocabulary-internal boost.
/// Type B: 2 unrelated dense patterns with items `[65,75], [85,95]`.
/// Type C: 2 decoy events.
pub fn make_ex1_config(beta: f64, seed: u64) -> SyntheticConfig {
    let n_transactions: usize = 5000;
    let n_items: usize = 200;
    let p_base: f64 = 0.03;
    let event_duration: i64 = 300;

    let type_a_items: Vec<Vec<i64>> = vec![vec![5, 15], vec![25, 35], vec![45, 55]];
    let spacing = n_transactions as i64 / (type_a_items.len() as i64 + 1);

    let mut events = Vec::new();
    let mut planted = Vec::new();

    for (i, pat) in type_a_items.iter().enumerate() {
        let start = (spacing * (i as i64 + 1) - event_duration / 2).max(0);
        let end = (start + event_duration).min(n_transactions as i64 - 1);
        events.push(SyntheticEvent {
            name: format!("Event_{}", i + 1),
            start,
            end,
        });
        planted.push(PlantedPattern {
            items: pat.clone(),
            event_idx: i,
            boost_factor: beta,
            baseline_prob: p_base,
        });
    }

    // Type B: unrelated dense patterns
    let mut rng = StdRng::seed_from_u64(seed);
    let type_b_items: Vec<Vec<i64>> = vec![vec![65, 75], vec![85, 95]];
    let n_unrelated = 2;
    let mut unrelated = Vec::new();
    for i in 0..n_unrelated {
        let pat = &type_b_items[i % type_b_items.len()];
        let active_start = rng.gen_range(0..=(n_transactions as i64 - event_duration - 1));
        let active_end = (active_start + event_duration).min(n_transactions as i64 - 1);
        unrelated.push(UnrelatedPattern {
            items: pat.clone(),
            active_start,
            active_end,
            boost_factor: beta,
        });
    }

    // Type C: decoy events
    let n_decoy = 2;
    let mut decoys = Vec::new();
    for i in 0..n_decoy {
        let start = rng.gen_range(0..=(n_transactions as i64 - event_duration - 1));
        let end = (start + event_duration).min(n_transactions as i64 - 1);
        decoys.push(SyntheticEvent {
            name: format!("Decoy_{}", i + 1),
            start,
            end,
        });
    }

    SyntheticConfig {
        n_items,
        n_transactions,
        item_probs: Vec::new(),
        p_base,
        planted_patterns: planted,
        unrelated_patterns: unrelated,
        events,
        decoy_events: decoys,
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// EX1-OVERLAP: Two planted events with overlapping time windows.
///
/// E1=[800,1400] and E2=[1200,1800] overlap in [1200,1400].
/// Tests temporal disambiguation by proximity component.
pub fn make_ex1_overlap_config(seed: u64) -> SyntheticConfig {
    let p_base = 0.03;
    SyntheticConfig {
        n_items: 200,
        n_transactions: 5000,
        item_probs: Vec::new(),
        p_base,
        planted_patterns: vec![
            PlantedPattern {
                items: vec![5, 15],
                event_idx: 0,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
            PlantedPattern {
                items: vec![25, 35],
                event_idx: 1,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
            PlantedPattern {
                items: vec![45, 55],
                event_idx: 2,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
        ],
        events: vec![
            SyntheticEvent {
                name: "Event_1".into(),
                start: 800,
                end: 1400,
            },
            SyntheticEvent {
                name: "Event_2".into(),
                start: 1200,
                end: 1800,
            },
            SyntheticEvent {
                name: "Event_3".into(),
                start: 3200,
                end: 3800,
            },
        ],
        unrelated_patterns: vec![
            UnrelatedPattern {
                items: vec![65, 75],
                active_start: 2400,
                active_end: 2700,
                boost_factor: 0.3,
            },
            UnrelatedPattern {
                items: vec![85, 95],
                active_start: 4200,
                active_end: 4500,
                boost_factor: 0.3,
            },
        ],
        decoy_events: vec![
            SyntheticEvent {
                name: "Decoy_1".into(),
                start: 2800,
                end: 3100,
            },
            SyntheticEvent {
                name: "Decoy_2".into(),
                start: 4600,
                end: 4900,
            },
        ],
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// EX1-CONFOUND: Type B patterns deliberately placed near events.
///
/// Type B active windows overlap with planted event windows, creating
/// the hardest discrimination case.
pub fn make_ex1_confound_config(seed: u64) -> SyntheticConfig {
    let p_base = 0.03;
    SyntheticConfig {
        n_items: 200,
        n_transactions: 5000,
        item_probs: Vec::new(),
        p_base,
        planted_patterns: vec![
            PlantedPattern {
                items: vec![5, 15],
                event_idx: 0,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
            PlantedPattern {
                items: vec![25, 35],
                event_idx: 1,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
            PlantedPattern {
                items: vec![45, 55],
                event_idx: 2,
                boost_factor: 0.3,
                baseline_prob: p_base,
            },
        ],
        events: vec![
            SyntheticEvent {
                name: "Event_1".into(),
                start: 1100,
                end: 1400,
            },
            SyntheticEvent {
                name: "Event_2".into(),
                start: 2500,
                end: 2800,
            },
            SyntheticEvent {
                name: "Event_3".into(),
                start: 3800,
                end: 4100,
            },
        ],
        unrelated_patterns: vec![
            // Deliberately overlap with E1 and E2
            UnrelatedPattern {
                items: vec![65, 75],
                active_start: 1050,
                active_end: 1450,
                boost_factor: 0.3,
            },
            UnrelatedPattern {
                items: vec![85, 95],
                active_start: 2450,
                active_end: 2850,
                boost_factor: 0.3,
            },
        ],
        decoy_events: vec![
            SyntheticEvent {
                name: "Decoy_1".into(),
                start: 600,
                end: 900,
            },
            SyntheticEvent {
                name: "Decoy_2".into(),
                start: 4400,
                end: 4700,
            },
        ],
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// EX1-DENSE: High pattern/event count (2x baseline).
///
/// 6 planted + 4 Type B + 4 decoys = heavy multiple-testing burden.
/// Shorter events (200) to fit more without forced overlap.
pub fn make_ex1_dense_config(seed: u64) -> SyntheticConfig {
    let p_base = 0.03;
    let n: usize = 5000;
    let dur: i64 = 200;

    let items_a: Vec<Vec<i64>> = vec![
        vec![5, 15],
        vec![25, 35],
        vec![45, 55],
        vec![105, 115],
        vec![125, 135],
        vec![145, 155],
    ];
    let spacing = n as i64 / (items_a.len() as i64 + 1);

    let mut events = Vec::new();
    let mut planted = Vec::new();
    for (i, pat) in items_a.iter().enumerate() {
        let start = (spacing * (i as i64 + 1) - dur / 2).max(0);
        let end = (start + dur).min(n as i64 - 1);
        events.push(SyntheticEvent {
            name: format!("Event_{}", i + 1),
            start,
            end,
        });
        planted.push(PlantedPattern {
            items: pat.clone(),
            event_idx: i,
            boost_factor: 0.3,
            baseline_prob: p_base,
        });
    }

    let mut rng = StdRng::seed_from_u64(seed);
    let items_b: Vec<Vec<i64>> = vec![
        vec![65, 75],
        vec![85, 95],
        vec![165, 175],
        vec![185, 195],
    ];
    let mut unrelated = Vec::new();
    for pat in &items_b {
        let s = rng.gen_range(0..=(n as i64 - dur - 1));
        unrelated.push(UnrelatedPattern {
            items: pat.clone(),
            active_start: s,
            active_end: s + dur,
            boost_factor: 0.3,
        });
    }

    let mut decoys = Vec::new();
    for i in 0..4 {
        let s = rng.gen_range(0..=(n as i64 - dur - 1));
        decoys.push(SyntheticEvent {
            name: format!("Decoy_{}", i + 1),
            start: s,
            end: s + dur,
        });
    }

    SyntheticConfig {
        n_items: 200,
        n_transactions: n,
        item_probs: Vec::new(),
        p_base,
        planted_patterns: planted,
        unrelated_patterns: unrelated,
        events,
        decoy_events: decoys,
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// EX1-SHORT: Short event duration (80 instead of 300).
///
/// Tests sensitivity to transient signals (flash sales, brief campaigns).
pub fn make_ex1_short_config(seed: u64) -> SyntheticConfig {
    let p_base = 0.03;
    let n: usize = 5000;
    let dur: i64 = 80;

    let items_a: Vec<Vec<i64>> = vec![vec![5, 15], vec![25, 35], vec![45, 55]];
    let spacing = n as i64 / (items_a.len() as i64 + 1);

    let mut events = Vec::new();
    let mut planted = Vec::new();
    for (i, pat) in items_a.iter().enumerate() {
        let start = (spacing * (i as i64 + 1) - dur / 2).max(0);
        let end = (start + dur).min(n as i64 - 1);
        events.push(SyntheticEvent {
            name: format!("Event_{}", i + 1),
            start,
            end,
        });
        planted.push(PlantedPattern {
            items: pat.clone(),
            event_idx: i,
            boost_factor: 0.3,
            baseline_prob: p_base,
        });
    }

    let mut rng = StdRng::seed_from_u64(seed);
    let unrelated = vec![
        {
            let s = rng.gen_range(0..=(n as i64 - dur - 1));
            UnrelatedPattern {
                items: vec![65, 75],
                active_start: s,
                active_end: s + dur,
                boost_factor: 0.3,
            }
        },
        {
            let s = rng.gen_range(0..=(n as i64 - dur - 1));
            UnrelatedPattern {
                items: vec![85, 95],
                active_start: s,
                active_end: s + dur,
                boost_factor: 0.3,
            }
        },
    ];

    let mut decoys = Vec::new();
    for i in 0..2 {
        let s = rng.gen_range(0..=(n as i64 - dur - 1));
        decoys.push(SyntheticEvent {
            name: format!("Decoy_{}", i + 1),
            start: s,
            end: s + dur,
        });
    }

    SyntheticConfig {
        n_items: 200,
        n_transactions: n,
        item_probs: Vec::new(),
        p_base,
        planted_patterns: planted,
        unrelated_patterns: unrelated,
        events,
        decoy_events: decoys,
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// Compute Zipf-distributed per-item probabilities.
///
/// `p(item_k) = min(max_prob, C / k^alpha)` where C is chosen so that the
/// median item (`k = n_items / 2`) has probability approximately `median_target`.
fn zipf_item_probs(n_items: usize, alpha: f64, median_target: f64, max_prob: f64) -> Vec<f64> {
    let median_rank = n_items / 2;
    let c = median_target * (median_rank as f64).powf(alpha);
    (1..=n_items)
        .map(|k| (c / (k as f64).powf(alpha)).min(max_prob))
        .collect()
}

/// EX6 Zipf: Realistic item-frequency distribution.
///
/// Same signal structure as EX1 baseline (3 Type A + 2 Type B + 2 decoy)
/// but with Zipf-distributed base item frequencies.
pub fn make_ex6_zipf_config(zipf_alpha: f64, seed: u64) -> SyntheticConfig {
    let n_transactions: usize = 5000;
    let n_items: usize = 200;
    let event_duration: i64 = 300;
    let boost = 0.3;
    let median_target = 0.03;
    let max_prob = 0.10;

    let item_probs = zipf_item_probs(n_items, zipf_alpha, median_target, max_prob);

    let type_a_items: Vec<Vec<i64>> = vec![vec![5, 15], vec![25, 35], vec![45, 55]];
    let spacing = n_transactions as i64 / (type_a_items.len() as i64 + 1);

    let mut events = Vec::new();
    let mut planted = Vec::new();
    for (i, pat) in type_a_items.iter().enumerate() {
        let start = (spacing * (i as i64 + 1) - event_duration / 2).max(0);
        let end = (start + event_duration).min(n_transactions as i64 - 1);
        events.push(SyntheticEvent {
            name: format!("Event_{}", i + 1),
            start,
            end,
        });
        planted.push(PlantedPattern {
            items: pat.clone(),
            event_idx: i,
            boost_factor: boost,
            baseline_prob: median_target,
        });
    }

    // Type B: 2 unrelated dense patterns (high-rank / rare items)
    let mut rng = StdRng::seed_from_u64(seed);
    let type_b_items: Vec<Vec<i64>> = vec![vec![150, 160], vec![170, 180]];
    let mut unrelated = Vec::new();
    for pat in &type_b_items {
        let active_start = rng.gen_range(0..=(n_transactions as i64 - event_duration - 1));
        let active_end = (active_start + event_duration).min(n_transactions as i64 - 1);
        unrelated.push(UnrelatedPattern {
            items: pat.clone(),
            active_start,
            active_end,
            boost_factor: boost,
        });
    }

    // Type C: 2 decoy events
    let mut decoys = Vec::new();
    for i in 0..2 {
        let start = rng.gen_range(0..=(n_transactions as i64 - event_duration - 1));
        let end = (start + event_duration).min(n_transactions as i64 - 1);
        decoys.push(SyntheticEvent {
            name: format!("Decoy_{}", i + 1),
            start,
            end,
        });
    }

    SyntheticConfig {
        n_items,
        n_transactions,
        item_probs,
        p_base: median_target,
        planted_patterns: planted,
        unrelated_patterns: unrelated,
        events,
        decoy_events: decoys,
        correlated_pairs: Vec::new(),
        seed,
    }
}

/// Null experiment: NO planted signals, only random decoy events.
///
/// Under the null hypothesis, no event causes any pattern change.
/// All significant attributions are false positives.
pub fn make_null_config(seed: u64) -> SyntheticConfig {
    let n_transactions: usize = 5000;
    let n_events = 5;
    let event_duration: i64 = 300;

    let mut rng = StdRng::seed_from_u64(seed);
    let mut decoys = Vec::new();
    for i in 0..n_events {
        let start = rng.gen_range(0..=(n_transactions as i64 - event_duration - 1));
        let end = (start + event_duration).min(n_transactions as i64 - 1);
        decoys.push(SyntheticEvent {
            name: format!("NullEvent_{}", i + 1),
            start,
            end,
        });
    }

    SyntheticConfig {
        n_items: 200,
        n_transactions,
        item_probs: Vec::new(),
        p_base: 0.03,
        planted_patterns: Vec::new(),
        unrelated_patterns: Vec::new(),
        events: Vec::new(),
        decoy_events: decoys,
        correlated_pairs: Vec::new(),
        seed,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_make_ex1_config_structure() {
        let cfg = make_ex1_config(0.3, 42);
        assert_eq!(cfg.n_transactions, 5000);
        assert_eq!(cfg.n_items, 200);
        assert_eq!(cfg.planted_patterns.len(), 3);
        assert_eq!(cfg.unrelated_patterns.len(), 2);
        assert_eq!(cfg.decoy_events.len(), 2);
        assert_eq!(cfg.events.len(), 3);

        // Check planted pattern items
        assert_eq!(cfg.planted_patterns[0].items, vec![5, 15]);
        assert_eq!(cfg.planted_patterns[1].items, vec![25, 35]);
        assert_eq!(cfg.planted_patterns[2].items, vec![45, 55]);
    }

    #[test]
    fn test_make_ex1_overlap_config_overlapping_events() {
        let cfg = make_ex1_overlap_config(42);
        // E1 and E2 should overlap
        let e1 = &cfg.events[0];
        let e2 = &cfg.events[1];
        assert!(e1.end >= e2.start, "E1 and E2 should overlap");
    }

    #[test]
    fn test_make_ex1_confound_config_overlap() {
        let cfg = make_ex1_confound_config(42);
        // Type B patterns should overlap with events
        let u0 = &cfg.unrelated_patterns[0];
        let e0 = &cfg.events[0];
        assert!(u0.active_start <= e0.end && u0.active_end >= e0.start);
    }

    #[test]
    fn test_make_ex1_dense_config_counts() {
        let cfg = make_ex1_dense_config(42);
        assert_eq!(cfg.planted_patterns.len(), 6);
        assert_eq!(cfg.unrelated_patterns.len(), 4);
        assert_eq!(cfg.decoy_events.len(), 4);
    }

    #[test]
    fn test_make_ex1_short_config_duration() {
        let cfg = make_ex1_short_config(42);
        for event in &cfg.events {
            assert!(event.end - event.start <= 80);
        }
    }

    #[test]
    fn test_make_ex6_zipf_config_probs() {
        let cfg = make_ex6_zipf_config(1.0, 42);
        assert_eq!(cfg.item_probs.len(), 200);
        // Head items should have higher probability
        assert!(cfg.item_probs[0] > cfg.item_probs[99]);
        // All probabilities should be <= max_prob (0.10)
        for &p in &cfg.item_probs {
            assert!(p <= 0.10 + 1e-12);
        }
    }

    #[test]
    fn test_make_null_config_no_planted() {
        let cfg = make_null_config(42);
        assert!(cfg.planted_patterns.is_empty());
        assert!(cfg.events.is_empty());
        assert_eq!(cfg.decoy_events.len(), 5);
    }

    #[test]
    fn test_generate_synthetic_writes_files() {
        let cfg = SyntheticConfig {
            n_items: 10,
            n_transactions: 50,
            item_probs: Vec::new(),
            p_base: 0.1,
            planted_patterns: vec![PlantedPattern {
                items: vec![1, 2],
                event_idx: 0,
                boost_factor: 0.8,
                baseline_prob: 0.0,
            }],
            unrelated_patterns: vec![UnrelatedPattern {
                items: vec![5, 6],
                active_start: 20,
                active_end: 30,
                boost_factor: 0.5,
            }],
            events: vec![SyntheticEvent {
                name: "TestEvent".into(),
                start: 10,
                end: 25,
            }],
            decoy_events: vec![SyntheticEvent {
                name: "Decoy".into(),
                start: 35,
                end: 45,
            }],
            correlated_pairs: Vec::new(),
            seed: 123,
        };

        let tmp = tempfile::tempdir().unwrap();
        let out_dir = tmp.path().to_str().unwrap();
        let info = generate_synthetic(&cfg, out_dir);

        // Verify files exist
        assert!(Path::new(&info.txn_path).exists());
        assert!(Path::new(&info.events_path).exists());
        assert!(Path::new(&info.gt_path).exists());
        assert!(info.unrelated_path.is_some());
        assert!(Path::new(info.unrelated_path.as_ref().unwrap()).exists());

        // Verify transaction file has correct number of lines
        let txn_content = fs::read_to_string(&info.txn_path).unwrap();
        let lines: Vec<&str> = txn_content.lines().collect();
        assert_eq!(lines.len(), 50);

        // Verify events JSON
        let events_content = fs::read_to_string(&info.events_path).unwrap();
        let events: Vec<serde_json::Value> = serde_json::from_str(&events_content).unwrap();
        assert_eq!(events.len(), 2); // 1 real + 1 decoy

        // Verify ground truth JSON
        let gt_content = fs::read_to_string(&info.gt_path).unwrap();
        let gt: Vec<serde_json::Value> = serde_json::from_str(&gt_content).unwrap();
        assert_eq!(gt.len(), 1);
        assert_eq!(gt[0]["event_id"], "E1");
    }

    #[test]
    fn test_zipf_item_probs_median() {
        let probs = zipf_item_probs(200, 1.0, 0.03, 0.10);
        let median_rank = 100; // n_items / 2
        // Median item should be close to median_target
        assert!((probs[median_rank - 1] - 0.03).abs() < 0.005);
    }
}
