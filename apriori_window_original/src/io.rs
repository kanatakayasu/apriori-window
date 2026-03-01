use std::collections::HashMap;
use std::fs::{create_dir_all, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;

use itertools::Itertools;

pub fn read_text_file_as_2d_vec_of_integers(path: &str) -> Vec<Vec<i64>> {
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
        let items = line
            .split_whitespace()
            .map(|item| item.parse::<i64>().expect("invalid integer"))
            .collect();
        transactions.push(items);
    }
    transactions
}

pub fn write_output_csv(
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
