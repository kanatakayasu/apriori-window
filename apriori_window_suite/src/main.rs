//! apriori_window_suite バイナリエントリポイント
//!
//! 使い方:
//!   cargo run -- phase1 [settings.json]
//!
//! settings.json を省略した場合は data/settings.json を使用する。
//! Phase 2 (Event Attribution) は Python プロトタイプを使用:
//!   python3 apriori_window_suite/python/event_attribution.py [settings.json]

use std::env;
use std::path::PathBuf;
use std::time::Instant;

use apriori_window_suite::{
    find_dense_itemsets, read_transactions_with_baskets, write_patterns_csv,
};
use serde::Deserialize;

// ---------------------------------------------------------------------------
// 設定ファイル
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
// Phase 1 実行
// ---------------------------------------------------------------------------

/// Phase 1 を実行してパターン CSV を書き出す。
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
// main
// ---------------------------------------------------------------------------

fn main() {
    let mut args = env::args().skip(1);
    let phase = args.next().unwrap_or_else(|| {
        eprintln!("Usage: apriori_window_suite phase1 [settings.json]");
        std::process::exit(1);
    });

    let default_settings = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("data")
        .join("settings.json");
    let settings_path = args.next().map(PathBuf::from).unwrap_or(default_settings);
    let settings_str = settings_path.to_str().unwrap();

    let start = Instant::now();
    match phase.as_str() {
        "phase1" => {
            let out = run_phase1(settings_str);
            println!("パターン出力: {}", out.display());
        }
        _ => {
            eprintln!("Unknown phase: {phase}. Use 'phase1'.");
            eprintln!("Phase 2 (Event Attribution) は Python で実行:");
            eprintln!("  python3 apriori_window_suite/python/event_attribution.py [settings.json]");
            std::process::exit(1);
        }
    }
    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    println!("Elapsed time: {:.3} ms", elapsed_ms);
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
