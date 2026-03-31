//! ST Event Attribution Pipeline — CLI binary.
//!
//! Usage:
//!   # Run pipeline on existing data files
//!   st_pipeline run --txn transactions.txt --loc locations.txt \
//!     --events events.json --n-locations 10 --window 200 --threshold 3
//!
//!   # Generate synthetic ST data
//!   st_pipeline gen --out-dir data/st_ex1 --n-txn 10000 --n-locations 10
//!
//!   # Run full experiment (gen + pipeline + evaluate)
//!   st_pipeline experiment --scenario ex1 --out-dir results/ex1

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use serde::{Deserialize, Serialize};

use apriori_window_suite::st_correlator::{
    run_1d_baseline_pipeline, run_st_pipeline, read_spatial_events, read_transactions_flat,
    read_locations, STAttribution, STConfig,
};

// ---------------------------------------------------------------------------
// CLI argument parsing (minimal, no external crate)
// ---------------------------------------------------------------------------

fn print_usage() {
    eprintln!("ST Event Attribution Pipeline");
    eprintln!();
    eprintln!("USAGE:");
    eprintln!("  st_pipeline run   --txn FILE --loc FILE --events FILE [OPTIONS]");
    eprintln!("  st_pipeline gen   --out-dir DIR [OPTIONS]");
    eprintln!("  st_pipeline experiment --scenario NAME --out-dir DIR [OPTIONS]");
    eprintln!();
    eprintln!("RUN OPTIONS:");
    eprintln!("  --n-locations N   Number of spatial locations");
    eprintln!("  --window N        Window size (default: 200)");
    eprintln!("  --threshold N     Support threshold (default: 3)");
    eprintln!("  --patterns FILE   Pre-computed patterns (JSON array of arrays)");
    eprintln!("  --alpha F         Significance level (default: 0.10)");
    eprintln!("  --n-perms N       Permutation replicates (default: 1000)");
    eprintln!("  --seed N          Random seed");
    eprintln!("  --out FILE        Output JSON file (default: stdout)");
    eprintln!();
    eprintln!("GEN OPTIONS:");
    eprintln!("  --n-txn N         Number of transactions (default: 10000)");
    eprintln!("  --n-locations N   Number of locations (default: 10)");
    eprintln!("  --n-items N       Base vocabulary size (default: 200)");
    eprintln!("  --p-base F        Base item probability (default: 0.02)");
    eprintln!("  --seed N          Random seed (default: 42)");
    eprintln!();
    eprintln!("EXPERIMENT SCENARIOS: ex1, ex2, ex3, ex4, ex5");
}

struct Args {
    command: String,
    kvs: HashMap<String, String>,
}

impl Args {
    fn parse() -> Self {
        let args: Vec<String> = std::env::args().skip(1).collect();
        if args.is_empty() {
            print_usage();
            std::process::exit(1);
        }
        let command = args[0].clone();
        let mut kvs = HashMap::new();
        let mut i = 1;
        while i < args.len() {
            if args[i].starts_with("--") {
                let key = args[i].clone();
                if i + 1 < args.len() && !args[i + 1].starts_with("--") {
                    kvs.insert(key, args[i + 1].clone());
                    i += 2;
                } else {
                    kvs.insert(key, "true".to_string());
                    i += 1;
                }
            } else {
                i += 1;
            }
        }
        Args { command, kvs }
    }

    fn get(&self, key: &str) -> Option<&str> {
        self.kvs.get(key).map(|s| s.as_str())
    }

    fn get_usize(&self, key: &str, default: usize) -> usize {
        self.get(key).map(|s| s.parse().unwrap()).unwrap_or(default)
    }

    fn get_f64(&self, key: &str, default: f64) -> f64 {
        self.get(key).map(|s| s.parse().unwrap()).unwrap_or(default)
    }
}

// ---------------------------------------------------------------------------
// Synthetic data generation
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PlantedSignal {
    pattern: Vec<i64>,
    event_id: String,
    event_name: String,
    start: usize,
    end: usize,
    spatial_scope: Vec<usize>,
    boost_factor: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DecoyEvent {
    event_id: String,
    event_name: String,
    start: usize,
    end: usize,
    spatial_scope: Vec<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct UnrelatedDense {
    pattern: Vec<i64>,
    start: usize,
    end: usize,
    spatial_scope: Vec<usize>,
    boost_factor: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SyntheticSTConfig {
    n_transactions: usize,
    n_locations: usize,
    n_items: usize,
    p_base: f64,
    signals: Vec<PlantedSignal>,
    decoys: Vec<DecoyEvent>,
    unrelated: Vec<UnrelatedDense>,
    seed: u64,
}

#[derive(Debug, Serialize)]
struct GroundTruth {
    pattern: Vec<i64>,
    event_id: String,
}

fn generate_st_data(cfg: &SyntheticSTConfig, out_dir: &Path) {
    std::fs::create_dir_all(out_dir).expect("failed to create output directory");
    let mut rng = StdRng::seed_from_u64(cfg.seed);

    // Generate transactions and locations
    let mut transactions: Vec<HashSet<i64>> = Vec::with_capacity(cfg.n_transactions);
    let mut locations: Vec<usize> = Vec::with_capacity(cfg.n_transactions);

    for t in 0..cfg.n_transactions {
        let loc = rng.gen_range(0..cfg.n_locations);
        locations.push(loc);

        let mut items: HashSet<i64> = HashSet::new();
        // Base items from vocabulary
        for item in 1..=(cfg.n_items as i64) {
            if rng.gen::<f64>() < cfg.p_base {
                items.insert(item);
            }
        }

        // Planted signals: boost items from vocabulary within event scope
        for sig in &cfg.signals {
            if t >= sig.start && t <= sig.end && sig.spatial_scope.contains(&loc) {
                if rng.gen::<f64>() < sig.boost_factor {
                    for &item in &sig.pattern {
                        items.insert(item);
                    }
                }
            }
        }

        // Unrelated dense patterns (no event association)
        for ur in &cfg.unrelated {
            if t >= ur.start && t <= ur.end && ur.spatial_scope.contains(&loc) {
                if rng.gen::<f64>() < ur.boost_factor {
                    for &item in &ur.pattern {
                        items.insert(item);
                    }
                }
            }
        }

        transactions.push(items);
    }

    // Write transactions
    let txn_path = out_dir.join("transactions.txt");
    let mut txn_buf = String::new();
    for txn in &transactions {
        let mut items: Vec<i64> = txn.iter().copied().collect();
        items.sort();
        let line: Vec<String> = items.iter().map(|x| x.to_string()).collect();
        txn_buf.push_str(&line.join(" "));
        txn_buf.push('\n');
    }
    std::fs::write(&txn_path, &txn_buf).expect("failed to write transactions");

    // Write locations
    let loc_path = out_dir.join("locations.txt");
    let loc_buf: String = locations.iter().map(|l| l.to_string() + "\n").collect();
    std::fs::write(&loc_path, &loc_buf).expect("failed to write locations");

    // Write events JSON
    let mut events: Vec<serde_json::Value> = Vec::new();
    for sig in &cfg.signals {
        events.push(serde_json::json!({
            "event_id": sig.event_id,
            "name": sig.event_name,
            "start": sig.start,
            "end": sig.end,
            "spatial_scope": sig.spatial_scope,
        }));
    }
    for dec in &cfg.decoys {
        events.push(serde_json::json!({
            "event_id": dec.event_id,
            "name": dec.event_name,
            "start": dec.start,
            "end": dec.end,
            "spatial_scope": dec.spatial_scope,
        }));
    }
    let events_path = out_dir.join("events.json");
    std::fs::write(&events_path, serde_json::to_string_pretty(&events).unwrap())
        .expect("failed to write events");

    // Write ground truth
    let gt: Vec<GroundTruth> = cfg
        .signals
        .iter()
        .map(|s| GroundTruth {
            pattern: s.pattern.clone(),
            event_id: s.event_id.clone(),
        })
        .collect();
    let gt_path = out_dir.join("ground_truth.json");
    std::fs::write(&gt_path, serde_json::to_string_pretty(&gt).unwrap())
        .expect("failed to write ground truth");

    // Write unrelated patterns
    let unrelated: Vec<serde_json::Value> = cfg
        .unrelated
        .iter()
        .map(|u| serde_json::json!({"pattern": u.pattern}))
        .collect();
    let ur_path = out_dir.join("unrelated_patterns.json");
    std::fs::write(&ur_path, serde_json::to_string_pretty(&unrelated).unwrap())
        .expect("failed to write unrelated patterns");

    // Write metadata
    let meta = serde_json::json!({
        "n_transactions": cfg.n_transactions,
        "n_locations": cfg.n_locations,
        "n_items": cfg.n_items,
        "p_base": cfg.p_base,
        "seed": cfg.seed,
        "n_signals": cfg.signals.len(),
        "n_decoys": cfg.decoys.len(),
        "n_unrelated": cfg.unrelated.len(),
    });
    std::fs::write(
        out_dir.join("metadata.json"),
        serde_json::to_string_pretty(&meta).unwrap(),
    )
    .expect("failed to write metadata");

    eprintln!(
        "Generated: {} txns, {} locations, {} signals, {} decoys, {} unrelated",
        cfg.n_transactions,
        cfg.n_locations,
        cfg.signals.len(),
        cfg.decoys.len(),
        cfg.unrelated.len(),
    );
}

// ---------------------------------------------------------------------------
// Pattern discovery (simple pair mining for experiments)
// ---------------------------------------------------------------------------

/// Find frequent item pairs using sliding window counts.
/// Returns patterns sorted by item IDs.
fn find_frequent_pairs(
    transactions: &[HashSet<i64>],
    locations: &[usize],
    window_t: usize,
    threshold: i32,
    n_locations: usize,
) -> Vec<Vec<i64>> {
    let n = transactions.len();
    if n < window_t {
        return Vec::new();
    }

    // Count co-occurrences across all windows and locations
    let mut pair_max_support: HashMap<(i64, i64), i32> = HashMap::new();

    // Per-location windowed counting
    for loc in 0..n_locations {
        let loc_indices: Vec<usize> = (0..n).filter(|&t| locations[t] == loc).collect();
        if loc_indices.is_empty() {
            continue;
        }

        // Simple approach: track pairs within window
        let mut pair_counts: HashMap<(i64, i64), i32> = HashMap::new();
        for &t in &loc_indices {
            let items: Vec<i64> = transactions[t].iter().copied().collect();
            for i in 0..items.len() {
                for j in (i + 1)..items.len() {
                    let (a, b) = if items[i] < items[j] {
                        (items[i], items[j])
                    } else {
                        (items[j], items[i])
                    };
                    *pair_counts.entry((a, b)).or_insert(0) += 1;
                }
            }
        }

        for (&pair, &count) in &pair_counts {
            let e = pair_max_support.entry(pair).or_insert(0);
            if count > *e {
                *e = count;
            }
        }
    }

    // Also do global pair counting (for 1D baseline comparison)
    let _global_counts: HashMap<(i64, i64), Vec<i32>> = HashMap::new();
    // Use approximate counting: total occurrences / (n / window_t)
    let mut total_pair_count: HashMap<(i64, i64), i32> = HashMap::new();
    for t in 0..n {
        let items: Vec<i64> = transactions[t].iter().copied().collect();
        for i in 0..items.len() {
            for j in (i + 1)..items.len() {
                let (a, b) = if items[i] < items[j] {
                    (items[i], items[j])
                } else {
                    (items[j], items[i])
                };
                *total_pair_count.entry((a, b)).or_insert(0) += 1;
            }
        }
    }

    // Filter: keep pairs with enough total occurrences
    let min_total = (threshold as f64 * 2.0) as i32;
    let mut patterns: Vec<Vec<i64>> = total_pair_count
        .iter()
        .filter(|(_, &count)| count >= min_total)
        .map(|(&(a, b), _)| vec![a, b])
        .collect();

    patterns.sort();
    patterns.dedup();

    eprintln!("  Found {} candidate pairs (threshold={})", patterns.len(), threshold);
    patterns
}

// ---------------------------------------------------------------------------
// Evaluation
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
struct EvalResult {
    precision: f64,
    recall: f64,
    f1: f64,
    tp: usize,
    fp: usize,
    #[serde(rename = "fn")]
    fn_count: usize,
    far: f64,
    n_predicted: usize,
}

fn evaluate(
    results: &[STAttribution],
    gt_path: &str,
    unrelated_path: &str,
) -> EvalResult {
    // Load ground truth
    let gt_text = std::fs::read_to_string(gt_path).unwrap_or_else(|_| "[]".to_string());
    let gt: Vec<serde_json::Value> = serde_json::from_str(&gt_text).unwrap();

    let gt_pairs: HashSet<(Vec<i64>, String)> = gt
        .iter()
        .map(|g| {
            let pattern: Vec<i64> = g["pattern"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_i64().unwrap())
                .collect();
            let event_id = g["event_id"].as_str().unwrap().to_string();
            (pattern, event_id)
        })
        .collect();

    // Load unrelated patterns
    let ur_text = std::fs::read_to_string(unrelated_path).unwrap_or_else(|_| "[]".to_string());
    let ur: Vec<serde_json::Value> = serde_json::from_str(&ur_text).unwrap();
    let unrelated_patterns: HashSet<Vec<i64>> = ur
        .iter()
        .map(|u| {
            let mut p: Vec<i64> = u["pattern"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_i64().unwrap())
                .collect();
            p.sort();
            p
        })
        .collect();

    let mut tp = 0usize;
    let mut fp = 0usize;
    let mut false_attributions = 0usize;

    for r in results {
        let mut pattern = r.pattern.clone();
        pattern.sort();

        if gt_pairs.contains(&(pattern.clone(), r.event_id.clone())) {
            tp += 1;
        } else {
            fp += 1;
            if unrelated_patterns.contains(&pattern) {
                false_attributions += 1;
            }
        }
    }

    let fn_count = gt_pairs.len().saturating_sub(tp);
    let precision = if tp + fp > 0 {
        tp as f64 / (tp + fp) as f64
    } else {
        0.0
    };
    let recall = if gt_pairs.is_empty() {
        0.0
    } else {
        tp as f64 / gt_pairs.len() as f64
    };
    let f1 = if precision + recall > 0.0 {
        2.0 * precision * recall / (precision + recall)
    } else {
        0.0
    };
    let far = if unrelated_patterns.is_empty() {
        0.0
    } else {
        false_attributions as f64 / unrelated_patterns.len() as f64
    };

    EvalResult {
        precision,
        recall,
        f1,
        tp,
        fp,
        fn_count,
        far,
        n_predicted: results.len(),
    }
}

// ---------------------------------------------------------------------------
// Subcommand: run
// ---------------------------------------------------------------------------

fn cmd_run(args: &Args) {
    let txn_path = args.get("--txn").expect("--txn required");
    let loc_path = args.get("--loc").expect("--loc required");
    let events_path = args.get("--events").expect("--events required");
    let n_locations = args.get_usize("--n-locations", 10);
    let window_t = args.get_usize("--window", 200);
    let threshold = args.get_usize("--threshold", 3) as i32;

    eprintln!("Loading data...");
    let transactions = read_transactions_flat(txn_path);
    let locations = read_locations(loc_path);
    let events = read_spatial_events(events_path);

    eprintln!(
        "  {} transactions, {} locations, {} events",
        transactions.len(),
        n_locations,
        events.len()
    );

    // Load or discover patterns
    let patterns = if let Some(pat_path) = args.get("--patterns") {
        let text = std::fs::read_to_string(pat_path).expect("failed to read patterns");
        let parsed: Vec<Vec<i64>> = serde_json::from_str(&text).expect("invalid patterns JSON");
        parsed
    } else {
        find_frequent_pairs(&transactions, &locations, window_t, threshold, n_locations)
    };

    eprintln!("  {} candidate patterns", patterns.len());

    let config = STConfig {
        n_permutations: args.get_usize("--n-perms", 1000),
        alpha: args.get_f64("--alpha", 0.10),
        seed: args.get("--seed").map(|s| s.parse::<u64>().unwrap()),
        ..Default::default()
    };

    // ST pipeline
    eprintln!("Running ST pipeline...");
    let t0 = Instant::now();
    let st_results = run_st_pipeline(
        &transactions,
        &locations,
        n_locations,
        &patterns,
        &events,
        window_t,
        threshold,
        &config,
    );
    let st_time = t0.elapsed().as_secs_f64() * 1000.0;

    // 1D baseline
    eprintln!("Running 1D baseline...");
    let t0 = Instant::now();
    let bl_results = run_1d_baseline_pipeline(
        &transactions,
        &locations,
        n_locations,
        &patterns,
        &events,
        window_t,
        threshold,
        &config,
    );
    let bl_time = t0.elapsed().as_secs_f64() * 1000.0;

    // Output
    let output = serde_json::json!({
        "n_transactions": transactions.len(),
        "n_locations": n_locations,
        "n_patterns": patterns.len(),
        "window_t": window_t,
        "threshold": threshold,
        "st": {
            "n_significant": st_results.len(),
            "time_ms": st_time,
            "results": st_results,
        },
        "baseline_1d": {
            "n_significant": bl_results.len(),
            "time_ms": bl_time,
            "results": bl_results,
        },
    });

    if let Some(out_path) = args.get("--out") {
        std::fs::write(out_path, serde_json::to_string_pretty(&output).unwrap())
            .expect("failed to write output");
        eprintln!("Results written to {}", out_path);
    } else {
        println!("{}", serde_json::to_string_pretty(&output).unwrap());
    }

    eprintln!(
        "ST: {} significant ({:.0}ms), 1D: {} significant ({:.0}ms)",
        st_results.len(),
        st_time,
        bl_results.len(),
        bl_time
    );
}

// ---------------------------------------------------------------------------
// Subcommand: gen
// ---------------------------------------------------------------------------

fn cmd_gen(args: &Args) {
    let out_dir = PathBuf::from(args.get("--out-dir").expect("--out-dir required"));
    let n_txn = args.get_usize("--n-txn", 10000);
    let n_locations = args.get_usize("--n-locations", 10);
    let n_items = args.get_usize("--n-items", 200);
    let p_base = args.get_f64("--p-base", 0.02);
    let seed = args.get_usize("--seed", 42) as u64;

    let cfg = SyntheticSTConfig {
        n_transactions: n_txn,
        n_locations,
        n_items,
        p_base,
        signals: vec![
            PlantedSignal {
                pattern: vec![10, 20],
                event_id: "E_LOCAL".to_string(),
                event_name: "local_campaign".to_string(),
                start: n_txn / 4,
                end: n_txn / 4 + n_txn / 10,
                spatial_scope: (0..n_locations / 2).collect(),
                boost_factor: 0.4,
            },
            PlantedSignal {
                pattern: vec![30, 40],
                event_id: "E_REGIONAL".to_string(),
                event_name: "regional_promo".to_string(),
                start: n_txn / 2,
                end: n_txn / 2 + n_txn / 10,
                spatial_scope: (n_locations / 4..3 * n_locations / 4).collect(),
                boost_factor: 0.35,
            },
        ],
        decoys: vec![DecoyEvent {
            event_id: "DECOY".to_string(),
            event_name: "decoy_event".to_string(),
            start: 3 * n_txn / 4,
            end: 3 * n_txn / 4 + n_txn / 10,
            spatial_scope: (n_locations / 2..n_locations).collect(),
        }],
        unrelated: vec![UnrelatedDense {
            pattern: vec![50, 60],
            start: n_txn / 5,
            end: n_txn / 5 + n_txn / 10,
            spatial_scope: (2..7.min(n_locations)).collect(),
            boost_factor: 0.3,
        }],
        seed,
    };

    generate_st_data(&cfg, &out_dir);
}

// ---------------------------------------------------------------------------
// Subcommand: experiment
// ---------------------------------------------------------------------------

fn run_experiment_scenario(
    scenario: &str,
    out_dir: &Path,
    seed: u64,
    n_perms: usize,
) -> serde_json::Value {
    let data_dir = out_dir.join("data");

    match scenario {
        "ex1" => run_ex1(&data_dir, out_dir, seed, n_perms),
        "ex2" => run_ex2(&data_dir, out_dir, seed, n_perms),
        "ex3" => run_ex3(&data_dir, out_dir, seed, n_perms),
        "ex4" => run_ex4(out_dir, seed, n_perms),
        _ => {
            eprintln!("Unknown scenario: {}. Available: ex1, ex2, ex3, ex4", scenario);
            std::process::exit(1);
        }
    }
}

/// EX1: Core attribution accuracy with in-vocabulary signals.
fn run_ex1(data_dir: &Path, out_dir: &Path, _seed: u64, n_perms: usize) -> serde_json::Value {
    eprintln!("=== EX1: Core Attribution Accuracy ===");

    let n_txn = 10000;
    let n_locations = 10;
    let window_t = 200;
    let threshold = 3;
    let betas = [0.1, 0.2, 0.3, 0.5];
    let seeds = [42, 123, 456, 789, 1024];

    let mut all_results = Vec::new();

    for &beta in &betas {
        let mut beta_results = Vec::new();

        for &s in &seeds {
            let run_dir = data_dir.join(format!("b{}_s{}", (beta * 100.0) as i32, s));

            let cfg = SyntheticSTConfig {
                n_transactions: n_txn,
                n_locations,
                n_items: 200,
                p_base: 0.02,
                signals: vec![
                    PlantedSignal {
                        pattern: vec![10, 20],
                        event_id: "E_LOCAL".into(),
                        event_name: "local_campaign".into(),
                        start: 2000,
                        end: 4000,
                        spatial_scope: (0..5).collect(),
                        boost_factor: beta,
                    },
                    PlantedSignal {
                        pattern: vec![30, 40],
                        event_id: "E_REGIONAL".into(),
                        event_name: "regional_promo".into(),
                        start: 5000,
                        end: 7000,
                        spatial_scope: (3..8).collect(),
                        boost_factor: beta,
                    },
                ],
                decoys: vec![DecoyEvent {
                    event_id: "DECOY".into(),
                    event_name: "decoy_event".into(),
                    start: 7500,
                    end: 9000,
                    spatial_scope: (7..10).collect(),
                }],
                unrelated: vec![UnrelatedDense {
                    pattern: vec![50, 60],
                    start: 1000,
                    end: 3000,
                    spatial_scope: (2..7).collect(),
                    boost_factor: beta * 0.8,
                }],
                seed: s,
            };

            generate_st_data(&cfg, &run_dir);

            let txns = read_transactions_flat(run_dir.join("transactions.txt").to_str().unwrap());
            let locs = read_locations(run_dir.join("locations.txt").to_str().unwrap());
            let events = read_spatial_events(run_dir.join("events.json").to_str().unwrap());
            let patterns = find_frequent_pairs(&txns, &locs, window_t, threshold, n_locations);

            let config = STConfig {
                n_permutations: n_perms,
                alpha: 0.10,
                min_support_range: 2,
                seed: Some(s),
                ..Default::default()
            };

            let t0 = Instant::now();
            let st = run_st_pipeline(&txns, &locs, n_locations, &patterns, &events, window_t, threshold, &config);
            let st_time = t0.elapsed().as_secs_f64() * 1000.0;

            let t0 = Instant::now();
            let bl = run_1d_baseline_pipeline(&txns, &locs, n_locations, &patterns, &events, window_t, threshold, &config);
            let bl_time = t0.elapsed().as_secs_f64() * 1000.0;

            let gt_path = run_dir.join("ground_truth.json");
            let ur_path = run_dir.join("unrelated_patterns.json");
            let st_eval = evaluate(&st, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());
            let bl_eval = evaluate(&bl, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());

            eprintln!(
                "  β={:.1} seed={}: ST F1={:.3} P={:.3} R={:.3} FAR={:.2} ({:.0}ms) | 1D F1={:.3} P={:.3} R={:.3} FAR={:.2} ({:.0}ms)",
                beta, s,
                st_eval.f1, st_eval.precision, st_eval.recall, st_eval.far, st_time,
                bl_eval.f1, bl_eval.precision, bl_eval.recall, bl_eval.far, bl_time,
            );

            beta_results.push(serde_json::json!({
                "seed": s,
                "st": { "eval": st_eval, "time_ms": st_time, "n_patterns": patterns.len() },
                "baseline_1d": { "eval": bl_eval, "time_ms": bl_time },
            }));
        }

        // Aggregate across seeds
        let avg_st_f1: f64 = beta_results.iter()
            .map(|r| r["st"]["eval"]["f1"].as_f64().unwrap())
            .sum::<f64>() / seeds.len() as f64;
        let avg_bl_f1: f64 = beta_results.iter()
            .map(|r| r["baseline_1d"]["eval"]["f1"].as_f64().unwrap())
            .sum::<f64>() / seeds.len() as f64;

        eprintln!("  β={:.1} avg: ST F1={:.3}, 1D F1={:.3}", beta, avg_st_f1, avg_bl_f1);

        all_results.push(serde_json::json!({
            "beta": beta,
            "avg_st_f1": avg_st_f1,
            "avg_bl_f1": avg_bl_f1,
            "runs": beta_results,
        }));
    }

    let result = serde_json::json!({
        "experiment": "EX1",
        "description": "Core attribution accuracy with in-vocabulary signals",
        "parameters": {
            "n_transactions": n_txn,
            "n_locations": n_locations,
            "window_t": window_t,
            "threshold": threshold,
            "n_permutations": n_perms,
        },
        "results": all_results,
    });

    let out_path = out_dir.join("ex1_results.json");
    std::fs::write(&out_path, serde_json::to_string_pretty(&result).unwrap()).unwrap();
    eprintln!("EX1 results saved to {}", out_path.display());
    result
}

/// EX2: Score component ablation.
fn run_ex2(data_dir: &Path, out_dir: &Path, seed: u64, n_perms: usize) -> serde_json::Value {
    eprintln!("=== EX2: Score Component Ablation ===");

    let n_txn = 10000;
    let n_locations = 10;
    let window_t = 200;
    let threshold = 3;

    // Scenario A: prox_t matters — 2 dense intervals, one near event, one far
    // Scenario B: direction matters — support drops at event start (not matching Up)
    // Scenario C: magnitude matters — 2 events, one large change, one small

    let scenarios = ["A_prox", "B_dir", "C_mag"];
    let ablation_modes = ["full", "no_dir", "no_prox", "no_mag", "mag_only", "prox_only"];

    let mut all_results = Vec::new();

    for scenario in &scenarios {
        let run_dir = data_dir.join(format!("ex2_{}", scenario));

        let cfg = match *scenario {
            "A_prox" => SyntheticSTConfig {
                n_transactions: n_txn,
                n_locations,
                n_items: 200,
                p_base: 0.02,
                signals: vec![PlantedSignal {
                    pattern: vec![10, 20],
                    event_id: "E_CAUSAL".into(),
                    event_name: "causal_event".into(),
                    start: 3000,
                    end: 5000,
                    spatial_scope: (0..5).collect(),
                    boost_factor: 0.4,
                }],
                decoys: vec![],
                unrelated: vec![
                    // Dense interval far from event
                    UnrelatedDense {
                        pattern: vec![10, 20],
                        start: 8000,
                        end: 9500,
                        spatial_scope: (0..5).collect(),
                        boost_factor: 0.4,
                    },
                ],
                seed,
            },
            "B_dir" => SyntheticSTConfig {
                n_transactions: n_txn,
                n_locations,
                n_items: 200,
                p_base: 0.02,
                signals: vec![PlantedSignal {
                    pattern: vec![30, 40],
                    event_id: "E_RISE".into(),
                    event_name: "rising_event".into(),
                    start: 4000,
                    end: 7000,
                    spatial_scope: (0..5).collect(),
                    boost_factor: 0.35,
                }],
                decoys: vec![],
                unrelated: vec![],
                seed,
            },
            "C_mag" => SyntheticSTConfig {
                n_transactions: n_txn,
                n_locations,
                n_items: 200,
                p_base: 0.02,
                signals: vec![
                    PlantedSignal {
                        pattern: vec![50, 60],
                        event_id: "E_STRONG".into(),
                        event_name: "strong_event".into(),
                        start: 2000,
                        end: 4000,
                        spatial_scope: (0..5).collect(),
                        boost_factor: 0.5,
                    },
                    PlantedSignal {
                        pattern: vec![50, 60],
                        event_id: "E_WEAK".into(),
                        event_name: "weak_event".into(),
                        start: 6000,
                        end: 8000,
                        spatial_scope: (5..10).collect(),
                        boost_factor: 0.1,
                    },
                ],
                decoys: vec![],
                unrelated: vec![],
                seed,
            },
            _ => unreachable!(),
        };

        generate_st_data(&cfg, &run_dir);

        let txns = read_transactions_flat(run_dir.join("transactions.txt").to_str().unwrap());
        let locs = read_locations(run_dir.join("locations.txt").to_str().unwrap());
        let events = read_spatial_events(run_dir.join("events.json").to_str().unwrap());
        let patterns = find_frequent_pairs(&txns, &locs, window_t, threshold, n_locations);

        let mut scenario_results = Vec::new();

        for &mode in &ablation_modes {
            let config = STConfig {
                n_permutations: n_perms,
                alpha: 0.10,
                min_support_range: 2,
                seed: Some(seed),
                ..Default::default()
            };

            let t0 = Instant::now();
            let results = run_st_pipeline(
                &txns, &locs, n_locations, &patterns, &events, window_t, threshold, &config,
            );
            let elapsed = t0.elapsed().as_secs_f64() * 1000.0;

            let gt_path = run_dir.join("ground_truth.json");
            let ur_path = run_dir.join("unrelated_patterns.json");
            let eval = evaluate(&results, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());

            eprintln!(
                "  {} / {}: F1={:.3} P={:.3} R={:.3} ({:.0}ms)",
                scenario, mode, eval.f1, eval.precision, eval.recall, elapsed
            );

            scenario_results.push(serde_json::json!({
                "mode": mode,
                "eval": eval,
                "time_ms": elapsed,
            }));
        }

        all_results.push(serde_json::json!({
            "scenario": scenario,
            "runs": scenario_results,
        }));
    }

    let result = serde_json::json!({
        "experiment": "EX2",
        "description": "Score component ablation",
        "results": all_results,
    });

    let out_path = out_dir.join("ex2_results.json");
    std::fs::write(&out_path, serde_json::to_string_pretty(&result).unwrap()).unwrap();
    eprintln!("EX2 results saved to {}", out_path.display());
    result
}

/// EX3: Parameter sensitivity.
fn run_ex3(data_dir: &Path, out_dir: &Path, seed: u64, n_perms: usize) -> serde_json::Value {
    eprintln!("=== EX3: Parameter Sensitivity ===");

    let n_txn = 10000;
    let n_locations = 10;
    let beta = 0.3;

    // Generate base data once
    let base_dir = data_dir.join("ex3_base");
    let cfg = SyntheticSTConfig {
        n_transactions: n_txn,
        n_locations,
        n_items: 200,
        p_base: 0.02,
        signals: vec![
            PlantedSignal {
                pattern: vec![10, 20],
                event_id: "E1".into(),
                event_name: "event_1".into(),
                start: 2000,
                end: 4000,
                spatial_scope: (0..5).collect(),
                boost_factor: beta,
            },
            PlantedSignal {
                pattern: vec![30, 40],
                event_id: "E2".into(),
                event_name: "event_2".into(),
                start: 5000,
                end: 7000,
                spatial_scope: (3..8).collect(),
                boost_factor: beta,
            },
        ],
        decoys: vec![DecoyEvent {
            event_id: "DECOY".into(),
            event_name: "decoy".into(),
            start: 7500,
            end: 9000,
            spatial_scope: (7..10).collect(),
        }],
        unrelated: vec![UnrelatedDense {
            pattern: vec![50, 60],
            start: 1000,
            end: 3000,
            spatial_scope: (2..7).collect(),
            boost_factor: 0.25,
        }],
        seed,
    };
    generate_st_data(&cfg, &base_dir);

    let txns = read_transactions_flat(base_dir.join("transactions.txt").to_str().unwrap());
    let locs = read_locations(base_dir.join("locations.txt").to_str().unwrap());
    let events = read_spatial_events(base_dir.join("events.json").to_str().unwrap());
    let gt_path = base_dir.join("ground_truth.json");
    let ur_path = base_dir.join("unrelated_patterns.json");

    let mut sweep_results = HashMap::new();

    // Sweep W
    let windows = [10, 20, 50, 100, 200];
    let mut w_results = Vec::new();
    for &w in &windows {
        let patterns = find_frequent_pairs(&txns, &locs, w, 3, n_locations);
        let config = STConfig {
            n_permutations: n_perms,
            alpha: 0.10,
            min_support_range: 2,
            seed: Some(seed),
            ..Default::default()
        };
        let results = run_st_pipeline(&txns, &locs, n_locations, &patterns, &events, w, 3, &config);
        let eval = evaluate(&results, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());
        eprintln!("  W={}: F1={:.3}", w, eval.f1);
        w_results.push(serde_json::json!({"W": w, "eval": eval}));
    }
    sweep_results.insert("window", serde_json::json!(w_results));

    // Sweep alpha
    let alphas = [0.01, 0.05, 0.10, 0.20, 0.30];
    let mut a_results = Vec::new();
    let patterns = find_frequent_pairs(&txns, &locs, 200, 3, n_locations);
    for &a in &alphas {
        let config = STConfig {
            n_permutations: n_perms,
            alpha: a,
            min_support_range: 2,
            seed: Some(seed),
            ..Default::default()
        };
        let results = run_st_pipeline(&txns, &locs, n_locations, &patterns, &events, 200, 3, &config);
        let eval = evaluate(&results, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());
        eprintln!("  α={}: F1={:.3}", a, eval.f1);
        a_results.push(serde_json::json!({"alpha": a, "eval": eval}));
    }
    sweep_results.insert("alpha", serde_json::json!(a_results));

    // Sweep B (permutations)
    let perms = [50, 100, 500, 1000, 5000];
    let mut b_results = Vec::new();
    for &b in &perms {
        let config = STConfig {
            n_permutations: b,
            alpha: 0.10,
            min_support_range: 2,
            seed: Some(seed),
            ..Default::default()
        };
        let results = run_st_pipeline(&txns, &locs, n_locations, &patterns, &events, 200, 3, &config);
        let eval = evaluate(&results, gt_path.to_str().unwrap(), ur_path.to_str().unwrap());
        eprintln!("  B={}: F1={:.3}", b, eval.f1);
        b_results.push(serde_json::json!({"B": b, "eval": eval}));
    }
    sweep_results.insert("permutations", serde_json::json!(b_results));

    let result = serde_json::json!({
        "experiment": "EX3",
        "description": "Parameter sensitivity",
        "sweep_results": sweep_results,
    });

    let out_path = out_dir.join("ex3_results.json");
    std::fs::write(&out_path, serde_json::to_string_pretty(&result).unwrap()).unwrap();
    eprintln!("EX3 results saved to {}", out_path.display());
    result
}

/// EX4: Scalability.
fn run_ex4(out_dir: &Path, seed: u64, n_perms: usize) -> serde_json::Value {
    eprintln!("=== EX4: Scalability ===");

    let data_dir = out_dir.join("data");
    let sizes = [1000, 5000, 10000, 50000, 100000];
    let n_events_list = [1, 3, 5, 10];
    let n_locations = 10;
    let window_t = 200;
    let threshold = 3;

    let mut all_results = Vec::new();

    for &n in &sizes {
        for &n_ev in &n_events_list {
            let run_dir = data_dir.join(format!("ex4_n{}_e{}", n, n_ev));

            // Generate signals
            let mut signals = Vec::new();
            let segment = n / (n_ev + 1);
            for i in 0..n_ev {
                signals.push(PlantedSignal {
                    pattern: vec![10 + 2 * i as i64, 11 + 2 * i as i64],
                    event_id: format!("E{}", i),
                    event_name: format!("event_{}", i),
                    start: (i + 1) * segment - segment / 2,
                    end: (i + 1) * segment + segment / 2,
                    spatial_scope: (0..n_locations / 2).collect(),
                    boost_factor: 0.3,
                });
            }

            let cfg = SyntheticSTConfig {
                n_transactions: n,
                n_locations,
                n_items: 200,
                p_base: 0.02,
                signals,
                decoys: vec![],
                unrelated: vec![],
                seed,
            };

            generate_st_data(&cfg, &run_dir);
            let txns = read_transactions_flat(run_dir.join("transactions.txt").to_str().unwrap());
            let locs = read_locations(run_dir.join("locations.txt").to_str().unwrap());
            let events = read_spatial_events(run_dir.join("events.json").to_str().unwrap());
            let patterns = find_frequent_pairs(&txns, &locs, window_t, threshold, n_locations);

            let config = STConfig {
                n_permutations: n_perms.min(200), // Fewer perms for scalability
                alpha: 0.10,
                min_support_range: 2,
                seed: Some(seed),
                ..Default::default()
            };

            let t0 = Instant::now();
            let _st = run_st_pipeline(
                &txns, &locs, n_locations, &patterns, &events, window_t, threshold, &config,
            );
            let st_time = t0.elapsed().as_secs_f64() * 1000.0;

            let t0 = Instant::now();
            let _bl = run_1d_baseline_pipeline(
                &txns, &locs, n_locations, &patterns, &events, window_t, threshold, &config,
            );
            let bl_time = t0.elapsed().as_secs_f64() * 1000.0;

            eprintln!(
                "  N={}, |E|={}: ST {:.0}ms, 1D {:.0}ms, patterns={}",
                n, n_ev, st_time, bl_time, patterns.len()
            );

            all_results.push(serde_json::json!({
                "n_transactions": n,
                "n_events": n_ev,
                "n_patterns": patterns.len(),
                "st_time_ms": st_time,
                "bl_time_ms": bl_time,
            }));
        }
    }

    let result = serde_json::json!({
        "experiment": "EX4",
        "description": "Scalability analysis",
        "results": all_results,
    });

    let out_path = out_dir.join("ex4_results.json");
    std::fs::write(&out_path, serde_json::to_string_pretty(&result).unwrap()).unwrap();
    eprintln!("EX4 results saved to {}", out_path.display());
    result
}

fn cmd_experiment(args: &Args) {
    let scenario = args.get("--scenario").expect("--scenario required");
    let out_dir = PathBuf::from(args.get("--out-dir").expect("--out-dir required"));
    let seed = args.get_usize("--seed", 42) as u64;
    let n_perms = args.get_usize("--n-perms", 1000);

    std::fs::create_dir_all(&out_dir).expect("failed to create output directory");
    run_experiment_scenario(scenario, &out_dir, seed, n_perms);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

fn main() {
    let args = Args::parse();
    match args.command.as_str() {
        "run" => cmd_run(&args),
        "gen" => cmd_gen(&args),
        "experiment" => cmd_experiment(&args),
        "help" | "--help" | "-h" => print_usage(),
        other => {
            eprintln!("Unknown command: {other}");
            print_usage();
            std::process::exit(1);
        }
    }
}
