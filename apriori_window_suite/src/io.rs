use std::collections::{HashMap, HashSet};
use std::fs::{create_dir_all, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;

use itertools::Itertools;

use crate::correlator::{format_itemset, Event, RelationMatch};

// ---------------------------------------------------------------------------
// Phase 1: トランザクション入出力
// ---------------------------------------------------------------------------

/// バスケット構造付きトランザクションファイルを読み込む。
///
/// 返り値: transactions[t][b][i]
///   t: トランザクションインデックス
///   b: バスケットインデックス（トランザクション内）
///   i: アイテムインデックス（バスケット内）
///
/// " | " を含まない行は単一バスケットとして扱う（旧フォーマット互換）。
pub fn read_transactions_with_baskets(path: &str) -> Vec<Vec<Vec<i64>>> {
    let file = File::open(path).expect("failed to open input file");
    let reader = BufReader::new(file);
    let mut transactions = Vec::new();
    for line in reader.lines() {
        let line = line.expect("failed to read line");
        let line = line.trim();
        if line.is_empty() {
            transactions.push(Vec::new());
            continue;
        }
        let baskets: Vec<Vec<i64>> = line
            .split(" | ")
            .map(|b| {
                b.split_whitespace()
                    .map(|x| x.parse::<i64>().expect("invalid integer"))
                    .collect()
            })
            .collect();
        transactions.push(baskets);
    }
    transactions
}

/// 密集アイテムセットを CSV ファイルに書き出す。
///
/// カラム: pattern_components, pattern_gaps, pattern_size, intervals_count, intervals
/// 単体アイテム（len == 1）はスキップする（Phase 1 の慣例）。
pub fn write_patterns_csv(
    output_path: &PathBuf,
    frequents: &HashMap<Vec<i64>, Vec<(i64, i64)>>,
) -> std::io::Result<()> {
    if let Some(parent) = output_path.parent() {
        create_dir_all(parent)?;
    }
    let file = File::create(output_path)?;
    let mut writer = BufWriter::new(file);
    writeln!(
        writer,
        "pattern_components,pattern_gaps,pattern_size,intervals_count,intervals"
    )?;

    let mut items: Vec<(&Vec<i64>, &Vec<(i64, i64)>)> = frequents.iter().collect();
    items.sort_by(|a, b| b.0.len().cmp(&a.0.len()).then_with(|| a.0.cmp(b.0)));

    for (itemset, intervals) in items {
        if itemset.len() <= 1 {
            continue;
        }
        let components_body = itemset.iter().map(|item| item.to_string()).join(", ");
        let pattern_components = format!("\"[{{{}}}]\"", components_body);
        let pattern_gaps = "\"[]\"";
        let intervals_count = intervals.len();
        let intervals_str = if intervals_count == 0 {
            "\"\"".to_string()
        } else {
            let joined = intervals
                .iter()
                .map(|(s, e)| format!("({},{})", s, e))
                .join(";");
            format!("\"{}\"", joined)
        };
        writeln!(
            writer,
            "{},{},{},{},{}",
            pattern_components,
            pattern_gaps,
            itemset.len(),
            intervals_count,
            intervals_str
        )?;
    }
    writer.flush()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Phase 2: イベント入出力
// ---------------------------------------------------------------------------

/// JSON 形式のイベントファイルを読み込む。
///
/// バリデーション:
///   - event_id の一意性を確認（重複 → panic）
///   - start <= end を確認（逆転 → panic）
pub fn read_events(path: &str) -> Vec<Event> {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|_| panic!("failed to read events file: {path}"));
    let raw: Vec<serde_json::Value> =
        serde_json::from_str(&text).expect("failed to parse events JSON");

    let mut events = Vec::new();
    let mut seen_ids: HashSet<String> = HashSet::new();

    for entry in &raw {
        let eid = entry["event_id"]
            .as_str()
            .expect("event_id must be a string")
            .to_string();
        if !seen_ids.insert(eid.clone()) {
            panic!("Duplicate event_id: {eid:?}");
        }
        let s = entry["start"].as_i64().expect("start must be an integer");
        let e = entry["end"].as_i64().expect("end must be an integer");
        if s > e {
            panic!("event_id={eid:?}: start({s}) > end({e})");
        }
        let name = entry["name"].as_str().unwrap_or("").to_string();
        events.push(Event {
            event_id: eid,
            name,
            start: s,
            end: e,
        });
    }
    events
}

/// 時間的関係マッチング結果を CSV ファイルに書き出す。
pub fn write_relations_csv(
    path: &PathBuf,
    results: &[RelationMatch],
    epsilon: i64,
    d_0: i64,
) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        create_dir_all(parent)?;
    }
    let file = File::create(path)?;
    let mut writer = BufWriter::new(file);
    writeln!(
        writer,
        "pattern_components,dense_start,dense_end,event_id,event_name,relation_type,overlap_length,epsilon,d_0"
    )?;
    for m in results {
        let overlap_str = match m.overlap_length {
            Some(v) => v.to_string(),
            None => String::new(),
        };
        writeln!(
            writer,
            "{},{},{},{},{},{},{},{},{}",
            format_itemset(&m.itemset),
            m.dense_start,
            m.dense_end,
            m.event_id,
            m.event_name,
            m.relation_type,
            overlap_str,
            epsilon,
            d_0,
        )?;
    }
    writer.flush()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// テスト (パーサー + read_events + write_relations_csv)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::correlator::RelationMatch;
    use std::io::Write as IoWrite;
    use tempfile::{NamedTempFile, TempDir};

    fn write_temp(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(content.as_bytes()).unwrap();
        f
    }

    // -----------------------------------------------------------------------
    // パーサー
    // -----------------------------------------------------------------------

    #[test]
    fn test_parse_single_basket() {
        let f = write_temp("1 2 3\n");
        let txns = read_transactions_with_baskets(f.path().to_str().unwrap());
        assert_eq!(txns, vec![vec![vec![1, 2, 3]]]);
    }

    #[test]
    fn test_parse_two_baskets() {
        let f = write_temp("1 2 | 3 4\n");
        let txns = read_transactions_with_baskets(f.path().to_str().unwrap());
        assert_eq!(txns, vec![vec![vec![1, 2], vec![3, 4]]]);
    }

    #[test]
    fn test_parse_three_baskets() {
        let f = write_temp("1 2 | 3 4 | 5\n");
        let txns = read_transactions_with_baskets(f.path().to_str().unwrap());
        assert_eq!(txns, vec![vec![vec![1, 2], vec![3, 4], vec![5]]]);
    }

    #[test]
    fn test_parse_empty_line() {
        let f = write_temp("\n1 2\n");
        let txns = read_transactions_with_baskets(f.path().to_str().unwrap());
        assert_eq!(txns, vec![vec![], vec![vec![1, 2]]]);
    }

    // -----------------------------------------------------------------------
    // TC-IO: read_events
    // -----------------------------------------------------------------------

    #[test]
    fn test_read_events_normal() {
        let json = r#"[{"event_id":"A","name":"Aname","start":1,"end":5}]"#;
        let f = write_temp(json);
        let events = read_events(f.path().to_str().unwrap());
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event_id, "A");
        assert_eq!(events[0].start, 1);
        assert_eq!(events[0].end, 5);
    }

    #[test]
    fn test_read_events_start_equals_end_ok() {
        let json = r#"[{"event_id":"A","name":"A","start":3,"end":3}]"#;
        let f = write_temp(json);
        let events = read_events(f.path().to_str().unwrap());
        assert_eq!(events[0].start, 3);
        assert_eq!(events[0].end, 3);
    }

    #[test]
    #[should_panic(expected = "Duplicate event_id")]
    fn test_read_events_duplicate_id_panics() {
        let json = r#"[
            {"event_id":"A","name":"A","start":1,"end":5},
            {"event_id":"A","name":"B","start":6,"end":10}
        ]"#;
        let f = write_temp(json);
        read_events(f.path().to_str().unwrap());
    }

    #[test]
    #[should_panic(expected = "start(5) > end(3)")]
    fn test_read_events_start_after_end_panics() {
        let json = r#"[{"event_id":"A","name":"A","start":5,"end":3}]"#;
        let f = write_temp(json);
        read_events(f.path().to_str().unwrap());
    }

    // -----------------------------------------------------------------------
    // TC-IO: write_relations_csv
    // -----------------------------------------------------------------------

    #[test]
    fn test_write_relations_csv_header() {
        let td = TempDir::new().unwrap();
        let path = td.path().join("r.csv");
        let results: Vec<RelationMatch> = Vec::new();
        write_relations_csv(&path, &results, 2, 1).unwrap();
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.starts_with("pattern_components,dense_start,dense_end,event_id"));
    }

    #[test]
    fn test_write_relations_csv_row() {
        let td = TempDir::new().unwrap();
        let path = td.path().join("r.csv");
        let results = vec![RelationMatch {
            itemset: vec![1, 2],
            dense_start: 0,
            dense_end: 5,
            event_id: "E1".to_string(),
            event_name: "Event1".to_string(),
            relation_type: "DenseFollowsEvent".to_string(),
            overlap_length: None,
        }];
        write_relations_csv(&path, &results, 2, 1).unwrap();
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("DenseFollowsEvent"));
        assert!(content.contains("E1"));
        assert!(content.contains(",,2,1") || content.contains(",,,"));
    }
}
