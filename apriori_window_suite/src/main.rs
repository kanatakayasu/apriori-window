//! apriori_window_suite バイナリエントリポイント
//!
//! 使い方:
//!   cargo run -- phase1 [settings.json]
//!   cargo run -- phase2 [settings.json]
//!
//! settings.json を省略した場合は data/settings.json を使用する。

use std::env;
use std::path::PathBuf;
use std::time::Instant;

use apriori_window_suite::{
    find_dense_itemsets, match_all, read_events, read_transactions_with_baskets,
    write_patterns_csv, write_relations_csv,
};
use serde::Deserialize;

// ---------------------------------------------------------------------------
// 設定ファイル（Phase 1 / Phase 2 共通）
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct Settings {
    input_file: InputFile,
    event_file: Option<EventFile>,
    output_files: OutputFiles,
    apriori_parameters: AprioriParameters,
    temporal_relation_parameters: Option<TemporalRelationParameters>,
}

#[derive(Deserialize)]
struct InputFile {
    dir: String,
    file_name: String,
}

#[derive(Deserialize)]
struct EventFile {
    dir: String,
    file_name: String,
}

#[derive(Deserialize)]
struct OutputFiles {
    dir: String,
    patterns_output_file_name: String,
    relations_output_file_name: Option<String>,
}

#[derive(Deserialize)]
struct AprioriParameters {
    window_size: usize,
    min_support: usize,
    max_length: usize,
}

#[derive(Deserialize)]
struct TemporalRelationParameters {
    epsilon: i64,
    d_0: i64,
}

// ---------------------------------------------------------------------------
// Phase 1 実行
// ---------------------------------------------------------------------------

/// Phase 1 を実行してパターン CSV を書き出す。
///
/// 返り値: patterns_output_path
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
// Phase 2 実行
// ---------------------------------------------------------------------------

/// Phase 2 を実行してパターン CSV と関係 CSV を書き出す。
///
/// event_file が設定されていない場合は Phase 1 のみ実行する（後退互換）。
///
/// 返り値: (patterns_path, Option<relations_path>)
fn run_phase2(settings_path: &str) -> (PathBuf, Option<PathBuf>) {
    let text = std::fs::read_to_string(settings_path)
        .unwrap_or_else(|_| panic!("failed to read settings: {settings_path}"));
    let settings: Settings = serde_json::from_str(&text).expect("failed to parse settings");

    let input_path =
        PathBuf::from(&settings.input_file.dir).join(&settings.input_file.file_name);
    let window_size = settings.apriori_parameters.window_size as i64;
    let threshold = settings.apriori_parameters.min_support;
    let max_length = settings.apriori_parameters.max_length;

    // --- Phase 1 ---
    let transactions = read_transactions_with_baskets(input_path.to_str().unwrap());
    let frequents = find_dense_itemsets(&transactions, window_size, threshold, max_length);

    let patterns_path = PathBuf::from(&settings.output_files.dir)
        .join(&settings.output_files.patterns_output_file_name);
    write_patterns_csv(&patterns_path, &frequents).expect("failed to write patterns csv");

    // --- Phase 2（event_file がある場合のみ）---
    let event_file_cfg = match &settings.event_file {
        Some(cfg) => cfg,
        None => return (patterns_path, None),
    };
    let relations_name = match &settings.output_files.relations_output_file_name {
        Some(name) => name.clone(),
        None => return (patterns_path, None),
    };

    let event_path = PathBuf::from(&event_file_cfg.dir).join(&event_file_cfg.file_name);
    let trp = settings.temporal_relation_parameters.as_ref();
    let epsilon = trp.map_or(0, |p| p.epsilon);
    let d_0 = trp.map_or(0, |p| p.d_0);

    let events = read_events(event_path.to_str().unwrap());
    let results = match_all(&frequents, &events, epsilon, d_0);

    let relations_path =
        PathBuf::from(&settings.output_files.dir).join(relations_name);
    write_relations_csv(&relations_path, &results, epsilon, d_0)
        .expect("failed to write relations csv");

    (patterns_path, Some(relations_path))
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

fn main() {
    let mut args = env::args().skip(1);
    let phase = args.next().unwrap_or_else(|| {
        eprintln!("Usage: apriori_window_suite <phase1|phase2> [settings.json]");
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
        "phase2" => {
            let (p, r) = run_phase2(settings_str);
            println!("パターン出力: {}", p.display());
            if let Some(rp) = r {
                println!("関係出力:     {}", rp.display());
            }
        }
        _ => {
            eprintln!("Unknown phase: {phase}. Use 'phase1' or 'phase2'.");
            std::process::exit(1);
        }
    }
    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    println!("Elapsed time: {:.3} ms", elapsed_ms);
}

// ---------------------------------------------------------------------------
// テスト (TC-E: run_phase1 / run_phase2 E2E)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn build_phase2_settings_json(
        txn_path: &std::path::Path,
        evt_path: Option<&std::path::Path>,
        out_dir: &std::path::Path,
        window_size: usize,
        min_support: usize,
        max_length: usize,
        epsilon: i64,
        d_0: i64,
    ) -> serde_json::Value {
        let mut s = serde_json::json!({
            "input_file": {
                "dir": txn_path.parent().unwrap().to_str().unwrap(),
                "file_name": txn_path.file_name().unwrap().to_str().unwrap()
            },
            "output_files": {
                "dir": out_dir.to_str().unwrap(),
                "patterns_output_file_name": "patterns.csv",
                "relations_output_file_name": "relations.csv"
            },
            "apriori_parameters": {
                "window_size": window_size,
                "min_support": min_support,
                "max_length": max_length
            },
            "temporal_relation_parameters": {
                "epsilon": epsilon,
                "d_0": d_0
            }
        });
        if let Some(ep) = evt_path {
            s["event_file"] = serde_json::json!({
                "dir": ep.parent().unwrap().to_str().unwrap(),
                "file_name": ep.file_name().unwrap().to_str().unwrap()
            });
        }
        s
    }

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

    #[test]
    fn test_run_phase2_outputs_created() {
        let td = tempfile::TempDir::new().unwrap();
        let txn = td.path().join("txn.txt");
        std::fs::write(&txn, "1 2\n1 2\n1 2\n").unwrap();
        let evt = td.path().join("events.json");
        std::fs::write(&evt, r#"[{"event_id":"A","name":"A","start":0,"end":10}]"#).unwrap();
        let out_dir = td.path().join("out");
        let settings =
            build_phase2_settings_json(&txn, Some(&evt), &out_dir, 2, 2, 2, 0, 1);
        let sf = td.path().join("settings.json");
        std::fs::write(&sf, serde_json::to_string(&settings).unwrap()).unwrap();

        let (p, r) = run_phase2(sf.to_str().unwrap());
        assert!(p.exists(), "patterns.csv should exist");
        assert!(r.is_some());
        assert!(r.unwrap().exists(), "relations.csv should exist");
    }

    #[test]
    fn test_run_phase2_relations_has_content() {
        let td = tempfile::TempDir::new().unwrap();
        let txn = td.path().join("txn.txt");
        std::fs::write(&txn, "1 2\n1 2\n1 2\n1 2\n").unwrap();
        let evt = td.path().join("events.json");
        std::fs::write(&evt, r#"[{"event_id":"A","name":"A","start":0,"end":100}]"#).unwrap();
        let out_dir = td.path().join("out");
        let settings =
            build_phase2_settings_json(&txn, Some(&evt), &out_dir, 2, 2, 2, 5, 1);
        let sf = td.path().join("settings.json");
        std::fs::write(&sf, serde_json::to_string(&settings).unwrap()).unwrap();

        let (_, r) = run_phase2(sf.to_str().unwrap());
        let r_path = r.unwrap();
        let content = std::fs::read_to_string(&r_path).unwrap();
        let lines: Vec<&str> = content.lines().collect();
        assert!(lines.len() > 1, "relations.csv should have data rows");
    }

    #[test]
    fn test_run_phase2_event_contains_dense_detected() {
        let td = tempfile::TempDir::new().unwrap();
        let txn = td.path().join("txn.txt");
        std::fs::write(&txn, "1 2\n1 2\n1 2\n1 2\n1 2\n").unwrap();
        let evt = td.path().join("events.json");
        std::fs::write(
            &evt,
            r#"[{"event_id":"BIG","name":"Big","start":-10,"end":100}]"#,
        )
        .unwrap();
        let out_dir = td.path().join("out");
        let settings =
            build_phase2_settings_json(&txn, Some(&evt), &out_dir, 2, 2, 2, 0, 1);
        let sf = td.path().join("settings.json");
        std::fs::write(&sf, serde_json::to_string(&settings).unwrap()).unwrap();

        let (_, r) = run_phase2(sf.to_str().unwrap());
        let content = std::fs::read_to_string(r.unwrap()).unwrap();
        assert!(content.contains("EventContainsDense"), "ECD expected in: {content}");
    }
}
