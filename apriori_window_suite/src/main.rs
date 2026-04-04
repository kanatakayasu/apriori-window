//! apriori_window_suite CLI
//!
//! Subcommands:
//!   phase1          Run Phase 1 (Apriori-window) from settings.json
//!   run-experiment  Run full attribution pipeline on given data
//!   run-ex3         Run EX3: method comparison experiment

use std::collections::{HashMap, HashSet};
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
    make_ex1_overlap_config, make_ex1_short_config, make_ex2_scenario_a_config,
    make_ex2_scenario_b_config, make_ex6_correlated_config, make_ex6_zipf_config,
    make_ex_pattern_length_config, make_null_fdr_config, scale_config_to_n, SyntheticConfig,
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
    /// Run EX2: score component ablation (Scenario A + B × 3 ablation modes)
    RunEx2 {
        /// Number of seeds
        #[arg(long, default_value_t = 5)]
        n_seeds: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/ex2")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/ex2")]
        data_dir: String,
    },
    /// Run pattern length robustness experiment (l=2,3,4)
    RunExPatternLength {
        /// Number of seeds
        #[arg(long, default_value_t = 20)]
        n_seeds: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/ex_pattern_length")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/ex_pattern_length")]
        data_dir: String,
    },
    /// Run item correlation robustness experiment (zipf_only vs zipf_corr)
    RunExRobustness {
        /// Number of seeds
        #[arg(long, default_value_t = 20)]
        n_seeds: usize,
        /// Output directory
        #[arg(long, default_value = "experiments/results/ex_robustness")]
        out_dir: String,
        /// Data directory
        #[arg(long, default_value = "experiments/data/ex_robustness")]
        data_dir: String,
    },
    /// Run EX4: Dunnhumby real campaign attribution
    RunEx4 {
        /// Path to Dunnhumby dataset directory
        #[arg(long, default_value = "dataset/dunnhumby")]
        data_dir: String,
        /// Output directory
        #[arg(long, default_value = "experiments/results/ex4_dunnhumby")]
        out_dir: String,
        /// Run sensitivity analysis (multiple W/θ settings)
        #[arg(long, default_value_t = true)]
        sensitivity: bool,
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

// ---------------------------------------------------------------------------
// EX2: Score Component Ablation
// ---------------------------------------------------------------------------

fn run_ex2(n_seeds: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(60));
    println!("EX2: Score Component Ablation");
    println!("{}", "=".repeat(60));

    let window_size: i64 = 1000;
    let min_support: usize = 100;

    let scenarios: Vec<(&str, Box<dyn Fn(u64) -> SyntheticConfig>)> = vec![
        ("A_prox_required", Box::new(|seed| make_ex2_scenario_a_config(seed))),
        ("B_mag_required", Box::new(|seed| make_ex2_scenario_b_config(seed))),
    ];
    let ablation_modes: &[(&str, Option<&str>)] = &[
        ("Full (prox*mag)", None),
        ("No proximity (mag only)", Some("no_prox")),
        ("No magnitude (prox only)", Some("no_mag")),
    ];

    let mut all_results: HashMap<String, serde_json::Value> = HashMap::new();

    for (scenario_name, config_fn) in &scenarios {
        println!("\n{}", "=".repeat(60));
        println!("Scenario {}", scenario_name);
        println!("{}", "=".repeat(60));

        let mut scenario_results: HashMap<String, serde_json::Value> = HashMap::new();

        for &(variant_name, ablation_mode) in ablation_modes {
            println!("\n  --- {} (mode={:?}) ---", variant_name, ablation_mode);
            let mut seed_results: Vec<ExperimentResult> = Vec::new();

            for seed in 0..n_seeds {
                let synth_config = config_fn(seed as u64);
                let mode_label = ablation_mode.unwrap_or("full");
                let seed_dir = format!("{}/{}/{}_seed{}", data_dir, scenario_name, mode_label, seed);
                let info = generate_synthetic(&synth_config, &seed_dir, window_size, min_support);

                // Load data and run with ablation
                let transactions = apriori_window_suite::io::read_transactions_with_baskets(&info.txn_path);
                let n_transactions = transactions.len() as i64;
                let (_, _, item_transaction_map) = apriori_window_suite::compute_item_basket_map(&transactions);
                let frequents = apriori_window_suite::find_dense_itemsets(&transactions, window_size, min_support, 2);
                let events = apriori_window_suite::io::read_events(&info.events_path);

                let t0 = std::time::Instant::now();
                let config = apriori_window_suite::correlator::AttributionConfig {
                    sigma: Some(window_size as f64),
                    n_permutations: 5000,
                    alpha: 0.10,
                    correction_method: "bh".to_string(),
                    global_correction: true,
                    deduplicate_overlap: true,
                    attribution_threshold: 0.1,
                    seed: Some(seed as u64),
                    ablation_mode: ablation_mode.map(|s| s.to_string()),
                    min_pattern_length: 2,
                    magnitude_normalization: "sqrt".to_string(),
                };

                let results = apriori_window_suite::correlator::run_attribution_pipeline(
                    &frequents,
                    &item_transaction_map,
                    &events,
                    window_size,
                    min_support as i64,
                    n_transactions,
                    &config,
                );

                let mut by_key: HashMap<(Vec<i64>, String), &apriori_window_suite::correlator::SignificantAttribution> = HashMap::new();
                for r in &results {
                    let key = (r.pattern.clone(), r.event_name.clone());
                    let entry = by_key.entry(key).or_insert(r);
                    if r.attribution_score > entry.attribution_score {
                        *entry = r;
                    }
                }
                let predicted: Vec<apriori_window_suite::evaluate::PredictedAttribution> = by_key.values().map(|r| {
                    apriori_window_suite::evaluate::PredictedAttribution {
                        pattern: r.pattern.clone(),
                        event_name: r.event_name.clone(),
                        interval_start: r.interval_start,
                        interval_end: r.interval_end,
                    }
                }).collect();

                let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
                let eval = apriori_window_suite::evaluate::evaluate_with_event_name_mapping(
                    &predicted, &info.gt_path, &info.events_path,
                );
                let far = if let Some(ref up) = info.unrelated_path {
                    if std::path::Path::new(up).exists() {
                        let fa = apriori_window_suite::evaluate::evaluate_false_attribution_rate(
                            &predicted, up, &info.events_path,
                        );
                        fa.false_attribution_rate
                    } else {
                        0.0
                    }
                } else {
                    0.0
                };

                println!(
                    "    seed={}: P={:.2} R={:.2} F1={:.2} FAR={:.2} {:.0}ms",
                    seed, eval.precision, eval.recall, eval.f1, far, elapsed_ms
                );
                seed_results.push(ExperimentResult {
                    method: variant_name.to_string(),
                    precision: eval.precision,
                    recall: eval.recall,
                    f1: eval.f1,
                    far,
                    n_pred: predicted.len(),
                    elapsed_ms,
                });
            }

            let n = seed_results.len() as f64;
            let avg_p: f64 = seed_results.iter().map(|r| r.precision).sum::<f64>() / n;
            let avg_r: f64 = seed_results.iter().map(|r| r.recall).sum::<f64>() / n;
            let avg_f1: f64 = seed_results.iter().map(|r| r.f1).sum::<f64>() / n;
            let avg_far: f64 = seed_results.iter().map(|r| r.far).sum::<f64>() / n;
            println!("    Average: P={:.2} R={:.2} F1={:.2} FAR={:.2}", avg_p, avg_r, avg_f1, avg_far);

            let seeds_json: Vec<serde_json::Value> = seed_results.iter().map(|r| serde_json::json!({
                "precision": r.precision,
                "recall": r.recall,
                "f1": r.f1,
                "false_attribution_rate": r.far,
                "n_pred": r.n_pred,
            })).collect();

            scenario_results.insert(variant_name.to_string(), serde_json::json!({
                "ablation_mode": ablation_mode,
                "seeds": seeds_json,
                "avg_precision": avg_p,
                "avg_recall": avg_r,
                "avg_f1": avg_f1,
                "avg_false_attribution_rate": avg_far,
            }));
        }

        all_results.insert(scenario_name.to_string(), serde_json::json!(scenario_results));
    }

    std::fs::create_dir_all(out_dir).ok();
    let save_path = format!("{}/ex2_results.json", out_dir);
    std::fs::write(&save_path, serde_json::to_string_pretty(&all_results).unwrap()).unwrap();
    println!("\nEX2 results saved to: {}", save_path);

    // Summary tables
    for (scenario_name, scenario_data) in &all_results {
        println!("\n{}", "=".repeat(70));
        println!("Scenario {}", scenario_name);
        println!("{:<30} {:>10} {:>8} {:>6} {:>6}", "Variant", "Precision", "Recall", "F1", "FAR");
        println!("{}", "-".repeat(70));
        if let Some(variants) = scenario_data.as_object() {
            for (variant, data) in variants {
                let p = data["avg_precision"].as_f64().unwrap_or(0.0);
                let r = data["avg_recall"].as_f64().unwrap_or(0.0);
                let f1 = data["avg_f1"].as_f64().unwrap_or(0.0);
                let far = data["avg_false_attribution_rate"].as_f64().unwrap_or(0.0);
                println!("{:<30} {:>10.2} {:>8.2} {:>6.2} {:>6.2}", variant, p, r, f1, far);
            }
        }
        println!("{}", "=".repeat(70));
    }
}

// ---------------------------------------------------------------------------
// Helpers for stats (CI computation)
// ---------------------------------------------------------------------------

fn compute_stats(values: &[f64]) -> (f64, f64, f64, f64, f64) {
    let n = values.len() as f64;
    let mean = values.iter().sum::<f64>() / n;
    if values.len() < 2 {
        return (mean, 0.0, 0.0, mean, mean);
    }
    let variance = values.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let std = variance.sqrt();
    let se = std / n.sqrt();
    let t_crit = 2.093_f64; // t_{0.025, df=19}
    let ci_lo = (mean - t_crit * se).max(0.0);
    let ci_hi = (mean + t_crit * se).min(1.0);
    (mean, std, se, ci_lo, ci_hi)
}

// ---------------------------------------------------------------------------
// EX-PATTERN-LENGTH: Pattern length robustness
// ---------------------------------------------------------------------------

fn run_ex_pattern_length(n_seeds: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(70));
    println!("Appendix: Pattern Length Robustness (l = 2, 3, 4)");
    println!("  Seeds: {} per length", n_seeds);
    println!("{}", "=".repeat(70));

    let window_size: i64 = 1000;
    let min_support: usize = 100;

    let mut all_results: HashMap<String, serde_json::Value> = HashMap::new();

    for length in [2usize, 3, 4] {
        let cond = format!("l={}", length);
        println!("\n--- {} ---", cond);
        let mut seed_results: Vec<ExperimentResult> = Vec::new();

        for seed in 0..n_seeds {
            let synth_config = make_ex_pattern_length_config(length, seed as u64);
            let seed_dir = format!("{}/l{}_seed{}", data_dir, length, seed);
            let info = generate_synthetic(&synth_config, &seed_dir, window_size, min_support);

            let r = run_experiment_method(
                &info.txn_path,
                &info.events_path,
                &info.gt_path,
                info.unrelated_path.as_deref(),
                "proposed",
                window_size, min_support, length, 0.10, 5000, seed as u64,
            );
            println!(
                "  seed={:2}: P={:.2} R={:.2} F1={:.2}",
                seed, r.precision, r.recall, r.f1
            );
            seed_results.push(r);
        }

        let f1_vals: Vec<f64> = seed_results.iter().map(|r| r.f1).collect();
        let p_vals: Vec<f64> = seed_results.iter().map(|r| r.precision).collect();
        let r_vals: Vec<f64> = seed_results.iter().map(|r| r.recall).collect();

        let (avg_f1, std_f1, se_f1, ci_lo, ci_hi) = compute_stats(&f1_vals);
        let avg_p: f64 = p_vals.iter().sum::<f64>() / n_seeds as f64;
        let avg_r: f64 = r_vals.iter().sum::<f64>() / n_seeds as f64;

        println!(
            "  Mean: P={:.2} R={:.2} F1={:.2} [95%CI: {:.2}–{:.2}] (std={:.3})",
            avg_p, avg_r, avg_f1, ci_lo, ci_hi, std_f1
        );

        let seeds_json: Vec<serde_json::Value> = seed_results.iter().map(|r| serde_json::json!({
            "precision": r.precision,
            "recall": r.recall,
            "f1": r.f1,
            "false_attribution_rate": r.far,
            "n_pred": r.n_pred,
        })).collect();

        all_results.insert(cond.clone(), serde_json::json!({
            "pattern_length": length,
            "seeds": seeds_json,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "std_f1": std_f1,
            "se_f1": se_f1,
            "ci95_lower": ci_lo,
            "ci95_upper": ci_hi,
        }));
    }

    std::fs::create_dir_all(out_dir).ok();
    let save_path = format!("{}/pattern_length_results.json", out_dir);
    std::fs::write(&save_path, serde_json::to_string_pretty(&all_results).unwrap()).unwrap();
    println!("\nResults saved to {}", save_path);

    println!("\n{}", "=".repeat(70));
    println!("{:<8} {:>6} {:>6} {:>6} {:>16} {:>6}", "Length", "Prec", "Rec", "F1", "95%CI", "std");
    println!("{}", "-".repeat(70));
    for length in [2usize, 3, 4] {
        let cond = format!("l={}", length);
        if let Some(data) = all_results.get(&cond) {
            let p = data["avg_precision"].as_f64().unwrap_or(0.0);
            let r = data["avg_recall"].as_f64().unwrap_or(0.0);
            let f1 = data["avg_f1"].as_f64().unwrap_or(0.0);
            let ci_lo = data["ci95_lower"].as_f64().unwrap_or(0.0);
            let ci_hi = data["ci95_upper"].as_f64().unwrap_or(0.0);
            let std = data["std_f1"].as_f64().unwrap_or(0.0);
            let ci_str = format!("[{:.2}, {:.2}]", ci_lo, ci_hi);
            println!("{:<8} {:>6.2} {:>6.2} {:>6.2} {:>16} {:>6.3}", cond, p, r, f1, ci_str, std);
        }
    }
    println!("{}", "=".repeat(70));
}

// ---------------------------------------------------------------------------
// EX-ROBUSTNESS: Item correlation robustness
// ---------------------------------------------------------------------------

fn run_ex_robustness(n_seeds: usize, out_dir: &str, data_dir: &str) {
    println!("{}", "=".repeat(70));
    println!("Appendix: Robustness under Item-Item Correlation");
    println!("  Seeds: {} per condition", n_seeds);
    println!("{}", "=".repeat(70));

    let window_size: i64 = 1000;
    let min_support: usize = 100;

    let conditions: Vec<(&str, Box<dyn Fn(u64) -> SyntheticConfig>)> = vec![
        ("zipf_only", Box::new(|seed| make_ex6_zipf_config(1.0, seed))),
        ("zipf_corr", Box::new(|seed| make_ex6_correlated_config(seed))),
    ];

    let mut all_results: HashMap<String, serde_json::Value> = HashMap::new();

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
                "  seed={:2}: P={:.2} R={:.2} F1={:.2} FAR={:.2}",
                seed, r.precision, r.recall, r.f1, r.far
            );
            seed_results.push(r);
        }

        let f1_vals: Vec<f64> = seed_results.iter().map(|r| r.f1).collect();
        let p_vals: Vec<f64> = seed_results.iter().map(|r| r.precision).collect();
        let r_vals: Vec<f64> = seed_results.iter().map(|r| r.recall).collect();
        let far_vals: Vec<f64> = seed_results.iter().map(|r| r.far).collect();

        let (avg_f1, std_f1, se_f1, ci_lo, ci_hi) = compute_stats(&f1_vals);
        let avg_p: f64 = p_vals.iter().sum::<f64>() / n_seeds as f64;
        let avg_r: f64 = r_vals.iter().sum::<f64>() / n_seeds as f64;
        let avg_far: f64 = far_vals.iter().sum::<f64>() / n_seeds as f64;

        println!(
            "  Mean: P={:.2} R={:.2} F1={:.2} [95%CI: {:.2}–{:.2}] FAR={:.2}",
            avg_p, avg_r, avg_f1, ci_lo, ci_hi, avg_far
        );

        let seeds_json: Vec<serde_json::Value> = seed_results.iter().map(|r| serde_json::json!({
            "precision": r.precision,
            "recall": r.recall,
            "f1": r.f1,
            "false_attribution_rate": r.far,
            "n_pred": r.n_pred,
        })).collect();

        all_results.insert(cond_name.to_string(), serde_json::json!({
            "seeds": seeds_json,
            "avg_precision": avg_p,
            "avg_recall": avg_r,
            "avg_f1": avg_f1,
            "std_f1": std_f1,
            "se_f1": se_f1,
            "ci95_lower": ci_lo,
            "ci95_upper": ci_hi,
            "avg_false_attribution_rate": avg_far,
        }));
    }

    std::fs::create_dir_all(out_dir).ok();
    let save_path = format!("{}/robustness_results.json", out_dir);
    std::fs::write(&save_path, serde_json::to_string_pretty(&all_results).unwrap()).unwrap();
    println!("\nResults saved to {}", save_path);

    println!("\n{}", "=".repeat(75));
    println!("{:<14} {:>6} {:>6} {:>6} {:>16} {:>6}", "Condition", "Prec", "Rec", "F1", "95%CI", "FAR");
    println!("{}", "-".repeat(75));
    for cond_name in ["zipf_only", "zipf_corr"] {
        if let Some(data) = all_results.get(cond_name) {
            let p = data["avg_precision"].as_f64().unwrap_or(0.0);
            let r = data["avg_recall"].as_f64().unwrap_or(0.0);
            let f1 = data["avg_f1"].as_f64().unwrap_or(0.0);
            let ci_lo = data["ci95_lower"].as_f64().unwrap_or(0.0);
            let ci_hi = data["ci95_upper"].as_f64().unwrap_or(0.0);
            let far = data["avg_false_attribution_rate"].as_f64().unwrap_or(0.0);
            let ci_str = format!("[{:.2}, {:.2}]", ci_lo, ci_hi);
            println!("{:<14} {:>6.2} {:>6.2} {:>6.2} {:>16} {:>6.2}", cond_name, p, r, f1, ci_str, far);
        }
    }
    println!("{}", "=".repeat(75));
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
// EX4: Dunnhumby real campaign attribution
// ---------------------------------------------------------------------------

/// アイテムパターンとクーポン対象商品の整合性を確認する。
fn is_coupon_consistent(
    pattern: &[i64],
    campaign_id: i64,
    coupon_map: &HashMap<i64, HashSet<i64>>,
) -> bool {
    if let Some(coupons) = coupon_map.get(&campaign_id) {
        pattern.iter().any(|item| coupons.contains(item))
    } else {
        false
    }
}

fn run_ex4(data_dir: &str, out_dir: &str, sensitivity: bool) {
    use csv::ReaderBuilder;

    let txn_path = format!("{}/transactions.txt", data_dir);
    let events_path = format!("{}/events.json", data_dir);
    let product_id_map_path = format!("{}/product_id_map.json", data_dir);
    let product_csv_path = format!("{}/raw/product.csv", data_dir);
    let coupon_csv_path = format!("{}/raw/coupon.csv", data_dir);

    // product_id_map: internal_id(str) -> original_pid(i64)
    let id_map_text =
        std::fs::read_to_string(&product_id_map_path).expect("failed to read product_id_map.json");
    let id_map_raw: HashMap<String, i64> =
        serde_json::from_str(&id_map_text).expect("failed to parse product_id_map.json");

    // 逆引き: original_pid -> internal_id
    let inv_id_map: HashMap<i64, i64> = id_map_raw
        .iter()
        .map(|(k, &v)| (v, k.parse::<i64>().expect("invalid internal id key")))
        .collect();

    // commodity map: internal_id -> commodity_desc
    let mut commodity_map: HashMap<i64, String> = HashMap::new();
    {
        let mut rdr = ReaderBuilder::new()
            .has_headers(true)
            .from_path(&product_csv_path)
            .expect("failed to open product.csv");
        for result in rdr.records() {
            let record = result.expect("failed to read product.csv record");
            // PRODUCT_ID,MANUFACTURER,DEPARTMENT,BRAND,COMMODITY_DESC,SUB_COMMODITY_DESC,...
            let pid: i64 = record[0].trim().parse().unwrap_or(-1);
            let commodity = record[4].trim().to_string();
            if let Some(&internal_id) = inv_id_map.get(&pid) {
                commodity_map.insert(internal_id, commodity);
            }
        }
    }

    // coupon map: campaign_id -> Set<internal_id>
    let mut coupon_map: HashMap<i64, HashSet<i64>> = HashMap::new();
    {
        let mut rdr = ReaderBuilder::new()
            .has_headers(true)
            .from_path(&coupon_csv_path)
            .expect("failed to open coupon.csv");
        for result in rdr.records() {
            let record = result.expect("failed to read coupon.csv record");
            // COUPON_UPC,PRODUCT_ID,CAMPAIGN
            let pid: i64 = record[1].trim().parse().unwrap_or(-1);
            let campaign_id: i64 = record[2].trim().parse().unwrap_or(-1);
            if let Some(&internal_id) = inv_id_map.get(&pid) {
                coupon_map.entry(campaign_id).or_default().insert(internal_id);
            }
        }
    }

    // 設定一覧
    let settings_list: Vec<(i64, usize, &str)> = if sensitivity {
        vec![
            (300, 5, "default"),
            (100, 3, "W100_t3"),
            (100, 5, "W100_t5"),
            (300, 3, "W300_t3"),
            (500, 5, "W500_t5"),
            (500, 10, "W500_t10"),
        ]
    } else {
        vec![(300, 5, "default")]
    };

    std::fs::create_dir_all(out_dir).expect("failed to create output directory");

    let mut all_results: Vec<serde_json::Value> = Vec::new();

    for (window_size, min_support, label) in &settings_list {
        let window_size = *window_size;
        let min_support = *min_support;

        println!("\n=== EX4: W={}, θ={} [{}] ===", window_size, min_support, label);

        // Phase 1
        let t_phase1_start = Instant::now();
        let transactions = read_transactions_with_baskets(&txn_path);
        let n_transactions = transactions.len() as i64;
        let (_, _, item_transaction_map) = compute_item_basket_map(&transactions);
        let frequents =
            find_dense_itemsets(&transactions, window_size, min_support, 100);
        let t_phase1 = t_phase1_start.elapsed().as_secs_f64();

        let n_patterns = frequents.keys().filter(|k| k.len() > 1).count();
        println!("  Transactions: {:}", n_transactions);
        println!("  Patterns: {}", n_patterns);
        println!("  Phase 1: {:.1}s", t_phase1);

        // TypeA イベントのみフィルタ
        let all_events = read_events(&events_path);
        let typea_events: Vec<_> =
            all_events.into_iter().filter(|e| e.name.contains("TypeA")).collect();
        let typea_names: Vec<String> = typea_events.iter().map(|e| e.name.clone()).collect();
        println!("  TypeA campaigns: {:?}", typea_names);

        // Attribution
        let config = AttributionConfig {
            sigma: Some(window_size as f64),
            n_permutations: 5000,
            alpha: 0.10,
            correction_method: "bh".to_string(),
            global_correction: true,
            deduplicate_overlap: true,
            attribution_threshold: 0.1,
            seed: Some(42),
            ablation_mode: None,
            min_pattern_length: 2,
            magnitude_normalization: "sqrt".to_string(),
        };

        let t_attr_start = Instant::now();
        let results = run_attribution_pipeline(
            &frequents,
            &item_transaction_map,
            &typea_events,
            window_size,
            min_support as i64,
            n_transactions,
            &config,
        );
        let t_attr = t_attr_start.elapsed().as_secs_f64();

        println!("  Attributions: {}", results.len());

        // クーポン整合性チェック
        let mut n_consistent = 0usize;
        let mut sig_list: Vec<serde_json::Value> = Vec::new();
        for r in &results {
            // event_id "C8" -> campaign_id 8
            // event.event_id を TypeA イベントから取得
            let campaign_id = typea_events
                .iter()
                .find(|e| e.name == r.event_name)
                .map(|e| e.event_id.trim_start_matches('C').parse::<i64>().unwrap_or(-1))
                .unwrap_or(-1);

            let cc = is_coupon_consistent(&r.pattern, campaign_id, &coupon_map);
            if cc {
                n_consistent += 1;
            }
            let cats: Vec<String> = r
                .pattern
                .iter()
                .map(|&id| {
                    commodity_map
                        .get(&id)
                        .cloned()
                        .unwrap_or_else(|| format!("ID:{}", id))
                })
                .collect();

            sig_list.push(serde_json::json!({
                "pattern_ids": r.pattern,
                "pattern_categories": cats,
                "event_name": r.event_name,
                "score": (r.attribution_score * 10000.0).round() / 10000.0,
                "p_adj": (r.adjusted_p_value * 10000.0).round() / 10000.0,
                "direction": r.change_direction,
                "coupon_consistent": cc,
            }));
        }

        let coupon_rate = if results.is_empty() {
            0.0f64
        } else {
            n_consistent as f64 / results.len() as f64
        };
        println!(
            "  Coupon match: {}/{} ({:.0}%)",
            n_consistent,
            results.len(),
            coupon_rate * 100.0
        );
        println!("  Attribution: {:.1}s", t_attr);

        // Campaign-level top patterns
        println!("\n  === Campaign Top Patterns ===");
        let mut by_campaign: HashMap<String, Vec<&serde_json::Value>> = HashMap::new();
        for r in &sig_list {
            let ev = r["event_name"].as_str().unwrap_or("").to_string();
            by_campaign.entry(ev).or_default().push(r);
        }

        let mut campaign_summary: Vec<serde_json::Value> = Vec::new();
        for ev in &typea_events {
            let campaign_id = ev.event_id.trim_start_matches('C').parse::<i64>().unwrap_or(-1);
            let mut attrs: Vec<&serde_json::Value> =
                by_campaign.get(&ev.name).cloned().unwrap_or_default();
            attrs.sort_by(|a, b| {
                b["score"]
                    .as_f64()
                    .unwrap_or(0.0)
                    .partial_cmp(&a["score"].as_f64().unwrap_or(0.0))
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            let top3: Vec<serde_json::Value> =
                attrs.iter().take(3).map(|v| (*v).clone()).collect();

            println!(
                "\n  {} (C{}): {} attributions",
                ev.name,
                campaign_id,
                attrs.len()
            );
            for r in &top3 {
                let cc_mark = if r["coupon_consistent"].as_bool().unwrap_or(false) {
                    "✓"
                } else {
                    "✗"
                };
                println!(
                    "    [{}] {:?}  score={:.3} p={:.4}",
                    cc_mark,
                    r["pattern_categories"],
                    r["score"].as_f64().unwrap_or(0.0),
                    r["p_adj"].as_f64().unwrap_or(0.0),
                );
            }

            campaign_summary.push(serde_json::json!({
                "campaign": ev.name,
                "campaign_id": campaign_id,
                "n_attributions": attrs.len(),
                "top_patterns": top3,
            }));
        }

        let output = serde_json::json!({
            "config": {
                "window_size": window_size,
                "min_support": min_support,
                "label": label,
            },
            "n_transactions": n_transactions,
            "n_patterns": n_patterns,
            "n_attributions": results.len(),
            "n_coupon_consistent": n_consistent,
            "coupon_consistency_rate": coupon_rate,
            "time_phase1_s": (t_phase1 * 10.0).round() / 10.0,
            "time_attribution_s": (t_attr * 10.0).round() / 10.0,
            "campaign_summary": campaign_summary,
            "all_attributions": sig_list,
        });

        let out_path = format!("{}/ex4_{}.json", out_dir, label);
        std::fs::write(&out_path, serde_json::to_string_pretty(&output).unwrap())
            .expect("failed to write output");
        println!("\n  Saved -> {}", out_path);

        all_results.push(output);
    }

    // 感度分析サマリ
    if sensitivity && all_results.len() > 1 {
        println!("\n{}", "=".repeat(70));
        println!(
            "{:<14} {:>5} {:>4} {:>6} {:>6} {:>12}",
            "Setting", "W", "θ", "#Pat", "#Attr", "CouponMatch"
        );
        println!("{}", "-".repeat(70));
        for res in &all_results {
            let cfg = &res["config"];
            let cc = res["n_coupon_consistent"].as_u64().unwrap_or(0);
            let tot = res["n_attributions"].as_u64().unwrap_or(0);
            let rate = res["coupon_consistency_rate"].as_f64().unwrap_or(0.0);
            println!(
                "{:<14} {:>5} {:>4} {:>6} {:>6}  {}/{} ({:.0}%)",
                cfg["label"].as_str().unwrap_or(""),
                cfg["window_size"].as_i64().unwrap_or(0),
                cfg["min_support"].as_i64().unwrap_or(0),
                res["n_patterns"].as_i64().unwrap_or(0),
                tot,
                cc,
                tot,
                rate * 100.0,
            );
        }
        println!("{}", "=".repeat(70));

        let sensitivity_path = format!("{}/ex4_sensitivity.json", out_dir);
        std::fs::write(
            &sensitivity_path,
            serde_json::to_string_pretty(&all_results).unwrap(),
        )
        .expect("failed to write sensitivity summary");
        println!(
            "Sensitivity saved -> {}",
            sensitivity_path
        );
    }
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
        Commands::RunEx2 { n_seeds, out_dir, data_dir } => {
            run_ex2(n_seeds, &out_dir, &data_dir);
        }
        Commands::RunExPatternLength { n_seeds, out_dir, data_dir } => {
            run_ex_pattern_length(n_seeds, &out_dir, &data_dir);
        }
        Commands::RunExRobustness { n_seeds, out_dir, data_dir } => {
            run_ex_robustness(n_seeds, &out_dir, &data_dir);
        }
        Commands::RunEx4 { data_dir, out_dir, sensitivity } => {
            run_ex4(&data_dir, &out_dir, sensitivity);
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
