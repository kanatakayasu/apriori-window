//! apriori_window_suite CLI
//!
//! Subcommands:
//!   phase1          Run Phase 1 (Apriori-window) from settings.json
//!   run-experiment  Run full attribution pipeline on given data
//!   run-ex3         Run EX3: method comparison experiment

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};

use apriori_window_suite::baselines::{BaselineParams, BaselineResult, PatternData};
use apriori_window_suite::correlator::{
    run_attribution_pipeline, AttributionConfig, SignificantAttribution,
};
use apriori_window_suite::evaluate::{
    evaluate_false_attribution_rate, evaluate_pattern_event_only,
    evaluate_with_event_name_mapping, PredictedAttribution,
};
use apriori_window_suite::io::{read_events, read_transactions_with_baskets};
use apriori_window_suite::synth::{
    generate_synthetic, make_ex1_config, make_ex1_confound_config, make_ex1_dense_config,
    make_ex1_overlap_config, make_ex1_short_config, make_ex6_zipf_config, make_null_fdr_config,
    scale_config_to_n, SyntheticConfig,
};
use apriori_window_suite::{
    compute_item_basket_map, find_dense_itemsets, write_patterns_csv,
};

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(name = "apriori_window_suite", about = "Apriori-window + Event Attribution Pipeline")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run Phase 1 from settings.json
    Phase1 {
        /// Path to settings.json
        #[arg(default_value = "data/settings.json")]
        settings: String,
    },
    /// Run experiment: Phase 1 + attribution + evaluation
    RunExperiment {
        /// Transaction file path
        #[arg(long)]
        txn: String,
        /// Events JSON path
        #[arg(long)]
        events: String,
        /// Ground truth JSON path
        #[arg(long)]
        gt: String,
        /// Method: proposed, wilcoxon, causalimpact, its, eventstudy, eca
        #[arg(long, default_value = "proposed")]
        method: String,
        /// Unrelated patterns JSON path (for FAR)
        #[arg(long)]
        unrelated: Option<String>,
        /// Window size
        #[arg(long, default_value_t = 50)]
        window_size: i64,
        /// Min support
        #[arg(long, default_value_t = 5)]
        min_support: usize,
        /// Max pattern length
        #[arg(long, default_value_t = 100)]
        max_length: usize,
        /// Alpha
        #[arg(long, default_value_t = 0.10)]
        alpha: f64,
        /// Number of permutations (proposed method)
        #[arg(long, default_value_t = 5000)]
        n_permutations: usize,
        /// Random seed
        #[arg(long, default_value_t = 0)]
        seed: u64,
        /// Output JSON path
        #[arg(long)]
        output: Option<String>,
    },
    /// Run EX1: core attribution accuracy
    RunEx1 {
        /// Number of seeds
        #[arg(long, default_value_t = 5)]
        n_seeds: usize,
        /// Number of transactions
        #[arg(long, default_value_t = 5000)]
        n_transactions: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/ex1")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/ex1")]
        data_dir: String,
    },
    /// Run EX3: method comparison experiment
    RunEx3 {
        /// Number of seeds
        #[arg(long, default_value_t = 5)]
        n_seeds: usize,
        /// Number of transactions
        #[arg(long, default_value_t = 5000)]
        n_transactions: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/method_comparison")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/method_comparison")]
        data_dir: String,
    },
    /// Run null FDR validation experiment
    RunNullFdr {
        /// Number of seeds
        #[arg(long, default_value_t = 20)]
        n_seeds: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/null_fdr")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/null_fdr")]
        data_dir: String,
    },
}

// ---------------------------------------------------------------------------
// Phase 1 settings
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct Settings {
    input_file: InputFile,
    output_files: OutputFiles,
    apriori_parameters: AprioriParameters,
}

#[derive(Deserialize)]
struct InputFile {
    dir: String,
    file_name: String,
}

#[derive(Deserialize)]
struct OutputFiles {
    dir: String,
    patterns_output_file_name: String,
}

#[derive(Deserialize)]
struct AprioriParameters {
    window_size: usize,
    min_support: usize,
    max_length: usize,
}

// ---------------------------------------------------------------------------
// Phase 1
// ---------------------------------------------------------------------------

fn run_phase1(settings_path: &str) -> PathBuf {
    let text = std::fs::read_to_string(settings_path)
        .unwrap_or_else(|_| panic!("failed to read settings: {settings_path}"));
    let settings: Settings = serde_json::from_str(&text).expect("failed to parse settings");

    let input_path =
        PathBuf::from(&settings.input_file.dir).join(&settings.input_file.file_name);
    let window_size = settings.apriori_parameters.window_size as i64;
    let threshold = settings.apriori_parameters.min_support;
    let max_length = settings.apriori_parameters.max_length;

    let transactions = read_transactions_with_baskets(input_path.to_str().unwrap());
    let frequents = find_dense_itemsets(&transactions, window_size, threshold, max_length);

    let patterns_path = PathBuf::from(&settings.output_files.dir)
        .join(&settings.output_files.patterns_output_file_name);
    write_patterns_csv(&patterns_path, &frequents).expect("failed to write patterns csv");

    patterns_path
}

// ---------------------------------------------------------------------------
// Run single experiment
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct ExperimentResult {
    method: String,
    precision: f64,
    recall: f64,
    f1: f64,
    far: f64,
    n_pred: usize,
    elapsed_ms: f64,
}

fn run_experiment_method(
    txn_path: &str,
    events_path: &str,
    gt_path: &str,
    unrelated_path: Option<&str>,
    method: &str,
    window_size: i64,
    min_support: usize,
    max_length: usize,
    alpha: f64,
    n_permutations: usize,
    seed: u64,
) -> ExperimentResult {
    let t0 = Instant::now();

    // Phase 1: load + mine
    let transactions = read_transactions_with_baskets(txn_path);
    let n_transactions = transactions.len() as i64;
    let (_, _, item_transaction_map) =
        compute_item_basket_map(&transactions);
    let frequents = find_dense_itemsets(&transactions, window_size, min_support, max_length);
    let events = read_events(events_path);

    let predicted: Vec<PredictedAttribution>;

    if method == "proposed" {
        // Run proposed method
        let config = AttributionConfig {
            sigma: Some(window_size as f64),
            n_permutations,
            alpha,
            correction_method: "bh".to_string(),
            global_correction: true,
            deduplicate_overlap: true,
            attribution_threshold: 0.1,
            seed: Some(seed),
            ablation_mode: None,
            min_pattern_length: 2,
            magnitude_normalization: "sqrt".to_string(),
        };

        let results = run_attribution_pipeline(
            &frequents,
            &item_transaction_map,
            &events,
            window_size,
            min_support as i64,
            n_transactions,
            &config,
        );

        // (P, E) 単位で重複排除し、最高帰属スコアの区間を保持
        let mut by_key: HashMap<(Vec<i64>, String), &SignificantAttribution> = HashMap::new();
        for r in &results {
            let key = (r.pattern.clone(), r.event_name.clone());
            let entry = by_key.entry(key).or_insert(r);
            if r.attribution_score > entry.attribution_score {
                *entry = r;
            }
        }
        predicted = by_key.values().map(|r| PredictedAttribution {
            pattern: r.pattern.clone(),
            event_name: r.event_name.clone(),
            interval_start: r.interval_start,
            interval_end: r.interval_end,
        }).collect();
    } else {
        // Run baseline
        let pattern_data = PatternData {
            frequents: frequents.clone(),
            item_transaction_map: item_transaction_map.clone(),
            n_transactions,
        };
        let params = BaselineParams {
            window_size,
            alpha,
            min_support_range: 0,
            deduplicate: true,
        };

        let baseline_results: Vec<BaselineResult> = match method {
            "wilcoxon" => apriori_window_suite::baselines::run_wilcoxon(&pattern_data, &events, &params),
            "causalimpact" => apriori_window_suite::baselines::run_causalimpact(&pattern_data, &events, &params),
            "its" => apriori_window_suite::baselines::run_its(&pattern_data, &events, &params),
            "eventstudy" => apriori_window_suite::baselines::run_event_study(&pattern_data, &events, &params),
            "eca" => apriori_window_suite::baselines::run_eca(&pattern_data, &events, &params),
            _ => panic!("Unknown method: {method}"),
        };

        predicted = baseline_results
            .iter()
            .map(|r| PredictedAttribution {
                pattern: r.pattern.clone(),
                event_name: r.event_name.clone(),
                interval_start: 0,
                interval_end: 0,
            })
            .collect();
    }

    let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

    // Evaluate: proposed uses (P,I,E) interval matching; baselines use (P,E) only
    // (baselines do not output interval information)
    let eval = if method == "proposed" {
        evaluate_with_event_name_mapping(&predicted, gt_path, events_path)
    } else {
        evaluate_pattern_event_only(&predicted, gt_path, events_path)
    };
    let far = if let Some(up) = unrelated_path {
        if std::path::Path::new(up).exists() {
            let fa = evaluate_false_attribution_rate(&predicted, up, events_path);
            fa.false_attribution_rate
        } else {
            0.0
        }
    } else {
        0.0
    };

    ExperimentResult {
        method: method.to_string(),
        precision: eval.precision,
        recall: eval.recall,
        f1: eval.f1,
        far,
        n_pred: predicted.len(),
        elapsed_ms,
    }
}

// ---------------------------------------------------------------------------
// EX3: Method Comparison
// ---------------------------------------------------------------------------

const METHOD_ORDER: &[&str] = &[
    "proposed", "wilcoxon", "causalimpact", "its", "eventstudy", "eca",
];
const METHOD_DISPLAY: &[&str] = &[
    "Proposed", "Wilcoxon", "CausalImpact", "ITS", "EventStudy", "ECA",
];

fn run_ex3(n_seeds: usize, n_transactions: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(90));
    println!("EX3: Method Comparison — {} Methods", METHOD_ORDER.len());
    println!("{}", "=".repeat(90));

    let conditions: Vec<(&str, Box<dyn Fn(u64) -> SyntheticConfig>)> = vec![
        ("β=0.3", Box::new(move |seed| {
            let c = make_ex6_zipf_config(1.0, seed);
            scale_config_to_n(&c, n_transactions)
        })),
        ("OVERLAP", Box::new(move |seed| {
            let c = make_ex1_overlap_config(seed);
            let mut c = scale_config_to_n(&c, n_transactions);
            c.item_probs = zipf_item_probs(c.n_items, 1.0, 0.03, 0.10);
            c
        })),
        ("CONFOUND", Box::new(move |seed| {
            let c = make_ex1_confound_config(seed);
            let mut c = scale_config_to_n(&c, n_transactions);
            c.item_probs = zipf_item_probs(c.n_items, 1.0, 0.03, 0.10);
            c
        })),
        ("DENSE", Box::new(move |seed| {
            let c = make_ex1_dense_config(seed);
            let mut c = scale_config_to_n(&c, n_transactions);
            c.item_probs = zipf_item_probs(c.n_items, 1.0, 0.03, 0.10);
            c
        })),
        ("SHORT", Box::new(move |seed| {
            let c = make_ex1_short_config(seed);
            let mut c = scale_config_to_n(&c, n_transactions);
            c.item_probs = zipf_item_probs(c.n_items, 1.0, 0.03, 0.10);
            c
        })),
    ];

    let window_size: i64 = 1000;
    // min_support=100: at N=100K W=1000, secondary patterns have E[support]≈9.9 << 100,
    // preventing secondary-pattern false attributions. Scales the N=5K setting (θ=5, W=50) by ×20.
    let min_support: usize = 100;

    let mut all_results: HashMap<String, HashMap<String, Vec<ExperimentResult>>> = HashMap::new();

    for (cond_name, config_fn) in &conditions {
        println!("\n--- {} ---", cond_name);
        let mut method_seeds: HashMap<String, Vec<ExperimentResult>> = HashMap::new();
        for m in METHOD_ORDER {
            method_seeds.insert(m.to_string(), Vec::new());
        }

        for seed in 0..n_seeds {
            let synth_config = config_fn(seed as u64);
            let cond_dir = cond_name.to_lowercase().replace('=', "");
            let seed_dir = format!("{}/{}_{}", data_dir, cond_dir, seed);
            let info = generate_synthetic(&synth_config, &seed_dir, window_size, min_support);

            for (i, &method) in METHOD_ORDER.iter().enumerate() {
                let r = run_experiment_method(
                    &info.txn_path,
                    &info.events_path,
                    &info.gt_path,
                    info.unrelated_path.as_deref(),
                    method,
                    window_size, min_support, 2, 0.10, 5000, seed as u64,
                ); // window_size=1000, min_support=100
                println!(
                    "  seed={} {:<14} P={:.2} R={:.2} F1={:.2} FAR={:.2} #={} {:.0}ms",
                    seed, METHOD_DISPLAY[i], r.precision, r.recall, r.f1, r.far,
                    r.n_pred, r.elapsed_ms
                );
                method_seeds.get_mut(method).unwrap().push(r);
            }
        }

        // Print averages
        println!("\n  {:<14} {:>6} {:>6} {:>6} {:>6}", "Method", "P", "R", "F1", "FAR");
        println!("  {}", "-".repeat(40));
        for (i, &method) in METHOD_ORDER.iter().enumerate() {
            let seeds = &method_seeds[method];
            let n = seeds.len() as f64;
            let avg_p: f64 = seeds.iter().map(|s| s.precision).sum::<f64>() / n;
            let avg_r: f64 = seeds.iter().map(|s| s.recall).sum::<f64>() / n;
            let avg_f1: f64 = seeds.iter().map(|s| s.f1).sum::<f64>() / n;
            let avg_far: f64 = seeds.iter().map(|s| s.far).sum::<f64>() / n;
            println!(
                "  {:<14} {:>6.2} {:>6.2} {:>6.2} {:>6.2}",
                METHOD_DISPLAY[i], avg_p, avg_r, avg_f1, avg_far
            );
        }

        all_results.insert(cond_name.to_string(), method_seeds);
    }

    // Save results
    std::fs::create_dir_all(out_dir).ok();
    let save_path = format!("{}/method_comparison_results.json", out_dir);

    // Convert to serializable format
    let mut serializable: HashMap<String, HashMap<String, Vec<SerializableResult>>> = HashMap::new();
    for (cond, methods) in &all_results {
        let mut m = HashMap::new();
        for (method, results) in methods {
            // Map method key to display name
            let display_idx = METHOD_ORDER.iter().position(|&x| x == method).unwrap();
            let display_name = METHOD_DISPLAY[display_idx];
            m.insert(
                display_name.to_string(),
                results.iter().map(|r| SerializableResult {
                    precision: r.precision,
                    recall: r.recall,
                    f1: r.f1,
                    far: r.far,
                    n_pred: r.n_pred,
                }).collect(),
            );
        }
        serializable.insert(cond.clone(), m);
    }

    let output = serde_json::json!({
        "results": serializable,
    });
    std::fs::write(&save_path, serde_json::to_string_pretty(&output).unwrap()).unwrap();
    println!("\nResults saved to: {}", save_path);
}

#[derive(Serialize)]
struct SerializableResult {
    precision: f64,
    recall: f64,
    f1: f64,
    far: f64,
    n_pred: usize,
}

// ---------------------------------------------------------------------------
// EX1: Core Attribution Accuracy
// ---------------------------------------------------------------------------

fn run_ex1(n_seeds: usize, n_transactions: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(90));
    println!("EX1: Core Attribution Accuracy — Proposed Method Only");
    println!("  Beta sweep: β ∈ {{0.1, 0.2, 0.3, 0.5}}");
    println!("  Structural: OVERLAP, CONFOUND, DENSE, SHORT");
    println!("  Seeds: {} per condition, N={}", n_seeds, n_transactions);
    println!("{}", "=".repeat(90));

    let conditions: Vec<(&str, Box<dyn Fn(u64) -> SyntheticConfig>)> = vec![
        ("beta_0.1", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_config(0.1, seed), n_transactions)
        })),
        ("beta_0.2", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_config(0.2, seed), n_transactions)
        })),
        ("beta_0.3", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_config(0.3, seed), n_transactions)
        })),
        ("beta_0.5", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_config(0.5, seed), n_transactions)
        })),
        ("OVERLAP", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_overlap_config(seed), n_transactions)
        })),
        ("CONFOUND", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_confound_config(seed), n_transactions)
        })),
        ("DENSE", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_dense_config(seed), n_transactions)
        })),
        ("SHORT", Box::new(move |seed| {
            scale_config_to_n(&make_ex1_short_config(seed), n_transactions)
        })),
    ];

    let window_size: i64 = 1000;
    // min_support=100: at N=100K W=1000, secondary patterns have E[support]≈9.9 << 100,
    // so only planted patterns (E[support]≈300) create dense intervals, preventing
    // secondary-pattern interference. Scales the N=5K setting (θ=5, W=50) by ×20.
    let min_support: usize = 100;

    let mut all_results: HashMap<String, Vec<ExperimentResult>> = HashMap::new();

    for (cond_name, config_fn) in &conditions {
        println!("\n--- {} ---", cond_name);
        let mut seed_results: Vec<ExperimentResult> = Vec::new();

        for seed in 0..n_seeds {
            let synth_config = config_fn(seed as u64);
            let seed_dir = format!("{}/{}_seed{}", data_dir, cond_name, seed);
            let info = generate_synthetic(&synth_config, &seed_dir, window_size, min_support);

            let r = run_experiment_method(
                &info.txn_path,
                &info.events_path,
                &info.gt_path,
                info.unrelated_path.as_deref(),
                "proposed",
                window_size, min_support, 2, 0.10, 5000, seed as u64,
            );
            println!(
                "  seed={}: P={:.2} R={:.2} F1={:.2} FAR={:.2} #={} {:.0}ms",
                seed, r.precision, r.recall, r.f1, r.far, r.n_pred, r.elapsed_ms
            );
            seed_results.push(r);
        }

        // Print averages
        let n = seed_results.len() as f64;
        let avg_p: f64 = seed_results.iter().map(|s| s.precision).sum::<f64>() / n;
        let avg_r: f64 = seed_results.iter().map(|s| s.recall).sum::<f64>() / n;
        let avg_f1: f64 = seed_results.iter().map(|s| s.f1).sum::<f64>() / n;
        let avg_far: f64 = seed_results.iter().map(|s| s.far).sum::<f64>() / n;
        println!("  Average: P={:.2} R={:.2} F1={:.2} FAR={:.2}", avg_p, avg_r, avg_f1, avg_far);

        all_results.insert(cond_name.to_string(), seed_results);
    }

    // Save results
    std::fs::create_dir_all(out_dir).ok();
    let save_path = format!("{}/ex1_results.json", out_dir);

    let mut serializable: HashMap<String, serde_json::Value> = HashMap::new();
    for (cond, results) in &all_results {
        let n = results.len() as f64;
        let seeds: Vec<serde_json::Value> = results.iter().map(|r| {
            serde_json::json!({
                "precision": r.precision,
                "recall": r.recall,
                "f1": r.f1,
                "far": r.far,
                "n_pred": r.n_pred,
                "elapsed_ms": r.elapsed_ms,
            })
        }).collect();
        serializable.insert(cond.clone(), serde_json::json!({
            "seeds": seeds,
            "avg_precision": results.iter().map(|r| r.precision).sum::<f64>() / n,
            "avg_recall": results.iter().map(|r| r.recall).sum::<f64>() / n,
            "avg_f1": results.iter().map(|r| r.f1).sum::<f64>() / n,
            "avg_false_attribution_rate": results.iter().map(|r| r.far).sum::<f64>() / n,
        }));
    }

    std::fs::write(&save_path, serde_json::to_string_pretty(&serializable).unwrap()).unwrap();
    println!("\nEX1 results saved to: {}", save_path);

    // Summary table
    println!("\n{}", "=".repeat(70));
    println!("{:<12} {:>10} {:>8} {:>6} {:>6}", "Condition", "Precision", "Recall", "F1", "FAR");
    println!("{}", "-".repeat(70));
    let cond_order = ["beta_0.1", "beta_0.2", "beta_0.3", "beta_0.5",
                      "OVERLAP", "CONFOUND", "DENSE", "SHORT"];
    for cond in cond_order {
        if let Some(results) = all_results.get(cond) {
            let n = results.len() as f64;
            let avg_p: f64 = results.iter().map(|r| r.precision).sum::<f64>() / n;
            let avg_r: f64 = results.iter().map(|r| r.recall).sum::<f64>() / n;
            let avg_f1: f64 = results.iter().map(|r| r.f1).sum::<f64>() / n;
            let avg_far: f64 = results.iter().map(|r| r.far).sum::<f64>() / n;
            println!("{:<12} {:>10.2} {:>8.2} {:>6.2} {:>6.2}", cond, avg_p, avg_r, avg_f1, avg_far);
        }
    }
    println!("{}", "=".repeat(70));
}

// ---------------------------------------------------------------------------
// Null FDR validation
// ---------------------------------------------------------------------------

fn run_null_fdr(n_seeds: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(70));
    println!("Null FDR Validation (α=0.10)");
    println!("  Dense intervals exist but are NOT caused by events");
    println!("  Expected: empirical FDR ≤ 0.10 across {} seeds", n_seeds);
    println!("{}", "=".repeat(70));

    let window_size: i64 = 1000;
    let min_support: usize = 100;
    let alpha = 0.10_f64;

    let config = AttributionConfig {
        n_permutations: 5000,
        alpha,
        correction_method: "bh".to_string(),
        global_correction: true,
        deduplicate_overlap: true,
        ..Default::default()
    };

    let mut total_discoveries = 0usize;
    let mut total_false = 0usize;
    let mut per_seed_fdr_sum = 0.0_f64;
    let mut seed_records: Vec<serde_json::Value> = Vec::new();

    for seed in 0..n_seeds {
        let synth_config = make_null_fdr_config(seed as u64);
        let seed_dir = format!("{}/seed{}", data_dir, seed);
        let info = generate_synthetic(&synth_config, &seed_dir, window_size, min_support);

        let transactions = read_transactions_with_baskets(&info.txn_path);
        let n_transactions = transactions.len() as i64;
        let (_, _, item_transaction_map) = compute_item_basket_map(&transactions);
        let frequents = find_dense_itemsets(&transactions, window_size, min_support, 2);
        let events = read_events(&info.events_path);

        let predictions = run_attribution_pipeline(
            &frequents,
            &item_transaction_map,
            &events,
            window_size,
            min_support as i64,
            n_transactions,
            &config,
        );

        // Under null: all significant attributions are false positives
        let n_sig = predictions.len();
        total_discoveries += n_sig;
        total_false += n_sig; // all are false under null
        // Per-seed FDR: V_i / max(R_i, 1). Average over seeds = mFDR.
        let seed_fdr = if n_sig == 0 { 0.0 } else { 1.0 }; // all discoveries are false
        per_seed_fdr_sum += seed_fdr;

        println!(
            "  seed={}: n_patterns={} n_significant={} (all FP)",
            seed, frequents.len(), n_sig,
        );

        seed_records.push(serde_json::json!({
            "seed": seed,
            "n_patterns": frequents.len(),
            "n_significant": n_sig,
            "fp": n_sig,
            "seed_fdr": seed_fdr,
        }));
    }

    // mean FDR per seed: average of (V_i / max(R_i, 1)) over seeds
    let mean_fdr = per_seed_fdr_sum / n_seeds as f64;
    // global FDR: total FP / total discoveries (another valid definition)
    let global_fdr = if total_discoveries == 0 {
        0.0
    } else {
        total_false as f64 / total_discoveries as f64
    };
    let avg_sig = total_discoveries as f64 / n_seeds as f64;
    let n_seeds_with_fp = seed_records.iter().filter(|r| r["fp"].as_u64().unwrap_or(0) > 0).count();

    println!("\n{}", "=".repeat(70));
    println!("Null FDR Summary:");
    println!("  Total seeds: {}", n_seeds);
    println!("  Average significant per seed: {:.2}", avg_sig);
    println!("  Seeds with ≥1 false positive: {}/{}", n_seeds_with_fp, n_seeds);
    println!("  Total discoveries: {} (all false)", total_discoveries);
    println!("  Mean per-seed FDR: {:.4} (threshold α={:.2})", mean_fdr, alpha);
    println!("  Global FDR: {:.4}", global_fdr);
    println!("  FDR controlled (mean): {}", if mean_fdr <= alpha { "YES" } else { "NO" });
    println!("{}", "=".repeat(70));

    let output = serde_json::json!({
        "n_seeds": n_seeds,
        "alpha": alpha,
        "total_discoveries": total_discoveries,
        "total_false": total_false,
        "mean_per_seed_fdr": mean_fdr,
        "global_fdr": global_fdr,
        "avg_significant_per_seed": avg_sig,
        "n_seeds_with_fp": n_seeds_with_fp,
        "fdr_controlled": mean_fdr <= alpha,
        "seeds": seed_records,
    });

    std::fs::create_dir_all(out_dir).unwrap();
    let save_path = format!("{}/null_fdr_results.json", out_dir);
    std::fs::write(&save_path, serde_json::to_string_pretty(&output).unwrap()).unwrap();
    println!("Results saved to: {}", save_path);
}

fn zipf_item_probs(n_items: usize, alpha: f64, median_target: f64, max_prob: f64) -> Vec<f64> {
    let median_rank = n_items as f64 / 2.0;
    let c = median_target * median_rank.powf(alpha);
    (0..n_items)
        .map(|k| {
            let rank = (k + 1) as f64;
            (c / rank.powf(alpha)).min(max_prob)
        })
        .collect()
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

fn main() {
    let cli = Cli::parse();
    let start = Instant::now();

    match cli.command {
        Commands::Phase1 { settings } => {
            let out = run_phase1(&settings);
            println!("パターン出力: {}", out.display());
        }
        Commands::RunExperiment {
            txn, events, gt, method, unrelated,
            window_size, min_support, max_length,
            alpha, n_permutations, seed, output,
        } => {
            let r = run_experiment_method(
                &txn, &events, &gt, unrelated.as_deref(),
                &method, window_size, min_support, max_length,
                alpha, n_permutations, seed,
            );
            let json = serde_json::to_string_pretty(&r).unwrap();
            if let Some(out_path) = output {
                std::fs::write(&out_path, &json).unwrap();
                println!("Results saved to: {}", out_path);
            } else {
                println!("{}", json);
            }
        }
        Commands::RunEx1 { n_seeds, n_transactions, out_dir, data_dir } => {
            run_ex1(n_seeds, n_transactions, &out_dir, &data_dir);
        }
        Commands::RunEx3 { n_seeds, n_transactions, out_dir, data_dir } => {
            run_ex3(n_seeds, n_transactions, &out_dir, &data_dir);
        }
        Commands::RunNullFdr { n_seeds, out_dir, data_dir } => {
            run_null_fdr(n_seeds, &out_dir, &data_dir);
        }
    }

    let elapsed = start.elapsed().as_secs_f64();
    println!("Total time: {:.1}s", elapsed);
}

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_run_phase1_outputs_created() {
        let td = tempfile::TempDir::new().unwrap();
        let txn = td.path().join("txn.txt");
        std::fs::write(&txn, "1 2\n1 2\n1 2\n").unwrap();
        let out_dir = td.path().join("out");
        let settings = serde_json::json!({
            "input_file": {
                "dir": td.path().to_str().unwrap(),
                "file_name": "txn.txt"
            },
            "output_files": {
                "dir": out_dir.to_str().unwrap(),
                "patterns_output_file_name": "patterns.csv"
            },
            "apriori_parameters": {
                "window_size": 2,
                "min_support": 2,
                "max_length": 2
            }
        });
        let sf = td.path().join("settings.json");
        std::fs::write(&sf, serde_json::to_string(&settings).unwrap()).unwrap();

        let p = run_phase1(sf.to_str().unwrap());
        assert!(p.exists(), "patterns.csv should exist");
    }
}
