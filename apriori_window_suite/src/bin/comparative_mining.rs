use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use rayon::prelude::*;
use std::cmp::{max, min};
use std::collections::{HashMap, HashSet};
use std::env;
use std::fs;

#[derive(Debug, Clone)]
struct Txn {
    ts: i64,
    items: Vec<i32>,
}

#[derive(Debug, Deserialize)]
struct Cli {
    method: String,
    input: String,
    input_format: String,
    params_json: String,
}

#[derive(Debug, Serialize)]
struct RustOutput {
    method: String,
    patterns: HashMap<String, usize>,
    intervals: HashMap<String, Vec<[i64; 2]>>,
    metadata: Value,
}

fn parse_args() -> Result<Cli, String> {
    let args: Vec<String> = env::args().collect();
    let mut method = None;
    let mut input = None;
    let mut input_format = None;
    let mut params_json = None;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--method" => {
                i += 1;
                method = args.get(i).cloned();
            }
            "--input" => {
                i += 1;
                input = args.get(i).cloned();
            }
            "--input-format" => {
                i += 1;
                input_format = args.get(i).cloned();
            }
            "--params-json" => {
                i += 1;
                params_json = args.get(i).cloned();
            }
            _ => {}
        }
        i += 1;
    }

    Ok(Cli {
        method: method.ok_or("missing --method")?,
        input: input.ok_or("missing --input")?,
        input_format: input_format.ok_or("missing --input-format")?,
        params_json: params_json.unwrap_or_else(|| "{}".to_string()),
    })
}

fn unique_sorted_items(items: impl Iterator<Item = i32>) -> Vec<i32> {
    let mut set: HashSet<i32> = HashSet::new();
    for x in items {
        set.insert(x);
    }
    let mut out: Vec<i32> = set.into_iter().collect();
    out.sort_unstable();
    out
}

fn parse_input(path: &str, input_format: &str) -> Result<Vec<Txn>, String> {
    let content = fs::read_to_string(path).map_err(|e| format!("read input failed: {e}"))?;
    let mut txns: Vec<Txn> = Vec::new();

    for (idx, line0) in content.lines().enumerate() {
        let line = line0.trim();
        if line.is_empty() {
            continue;
        }

        match input_format {
            "flat" => {
                let items = unique_sorted_items(
                    line.split_whitespace()
                        .filter_map(|x| x.parse::<i32>().ok()),
                );
                txns.push(Txn {
                    ts: idx as i64,
                    items,
                });
            }
            "basket" => {
                let mut raw: Vec<i32> = Vec::new();
                for b in line.split('|') {
                    for tok in b.split_whitespace() {
                        if let Ok(v) = tok.parse::<i32>() {
                            raw.push(v);
                        }
                    }
                }
                let items = unique_sorted_items(raw.into_iter());
                txns.push(Txn {
                    ts: idx as i64,
                    items,
                });
            }
            "timestamped" => {
                let mut it = line.split_whitespace();
                let ts = it
                    .next()
                    .ok_or("timestamped row missing ts")?
                    .parse::<i64>()
                    .map_err(|e| format!("bad ts: {e}"))?;
                let items = unique_sorted_items(it.filter_map(|x| x.parse::<i32>().ok()));
                txns.push(Txn { ts, items });
            }
            _ => return Err(format!("unknown input_format={input_format}")),
        }
    }

    txns.sort_by_key(|t| t.ts);
    Ok(txns)
}

fn combinations_of(items: &[i32], k: usize, out: &mut Vec<Vec<i32>>, cur: &mut Vec<i32>, start: usize) {
    if cur.len() == k {
        out.push(cur.clone());
        return;
    }
    for i in start..items.len() {
        cur.push(items[i]);
        combinations_of(items, k, out, cur, i + 1);
        cur.pop();
    }
}

fn enumerate_itemsets(
    txns: &[Txn],
    max_length: usize,
) -> (HashMap<Vec<i32>, usize>, HashMap<Vec<i32>, Vec<i64>>) {
    txns.par_iter()
        .map(|tx| {
            let mut counts: HashMap<Vec<i32>, usize> = HashMap::new();
            let mut ts_map: HashMap<Vec<i32>, Vec<i64>> = HashMap::new();
            let upto = min(max_length, tx.items.len());
            for k in 1..=upto {
                let mut combs = Vec::new();
                let mut cur = Vec::new();
                combinations_of(&tx.items, k, &mut combs, &mut cur, 0);
                for c in combs {
                    *counts.entry(c.clone()).or_insert(0) += 1;
                    ts_map.entry(c).or_default().push(tx.ts);
                }
            }
            (counts, ts_map)
        })
        .reduce(
            || (HashMap::new(), HashMap::new()),
            |mut a, b| {
                for (k, v) in b.0 {
                    *a.0.entry(k).or_insert(0) += v;
                }
                for (k, mut v) in b.1 {
                    a.1.entry(k).or_default().append(&mut v);
                }
                a
            },
        )
}

fn key_of(itemset: &[i32]) -> String {
    itemset
        .iter()
        .map(|x| x.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn minsup_count(params: &Value, n_txn: usize) -> usize {
    if let Some(v) = params.get("minsup_count").and_then(|x| x.as_u64()) {
        return v as usize;
    }
    if let Some(v) = params.get("minsup_ratio").and_then(|x| x.as_f64()) {
        return max(1, (v * n_txn as f64).ceil() as usize);
    }
    if let Some(v) = params.get("minsup").and_then(|x| x.as_u64()) {
        return v as usize;
    }
    if let Some(v) = params.get("minSup").and_then(|x| x.as_u64()) {
        return v as usize;
    }
    1
}

fn solve_pattern_family(method: &str, txns: &[Txn], params: &Value) -> RustOutput {
    let max_length = params
        .get("max_length")
        .and_then(|x| x.as_u64())
        .unwrap_or(4) as usize;
    let minsup = minsup_count(params, txns.len());
    let (counts, _) = enumerate_itemsets(txns, max_length);

    let patterns: HashMap<String, usize> = counts
        .into_par_iter()
        .filter_map(|(k, v)| {
            if v >= minsup {
                Some((key_of(&k), v))
            } else {
                None
            }
        })
        .collect();

    RustOutput {
        method: method.to_string(),
        patterns,
        intervals: HashMap::new(),
        metadata: json!({
            "impl": format!("rust_{}", method),
            "minsup_count": minsup,
            "max_length": max_length,
        }),
    }
}

fn periods(ts_list: &[i64], ts_fin: i64) -> Vec<i64> {
    if ts_list.is_empty() {
        return vec![];
    }
    let mut p = vec![ts_list[0]];
    for i in 1..ts_list.len() {
        p.push(ts_list[i] - ts_list[i - 1]);
    }
    p.push(ts_fin - ts_list[ts_list.len() - 1]);
    p
}

fn solve_pfpm(txns: &[Txn], params: &Value) -> RustOutput {
    let max_length = params
        .get("max_length")
        .and_then(|x| x.as_u64())
        .unwrap_or(4) as usize;
    let minsup = minsup_count(params, txns.len());
    let min_per = params.get("minPer").and_then(|x| x.as_i64()).unwrap_or(1);
    let max_per = params
        .get("maxPer")
        .and_then(|x| x.as_i64())
        .unwrap_or(i64::MAX / 4);
    let min_avg = params.get("minAvg").and_then(|x| x.as_f64()).unwrap_or(0.0);
    let max_avg = params
        .get("maxAvg")
        .and_then(|x| x.as_f64())
        .unwrap_or(f64::MAX / 4.0);

    let (counts, ts_map) = enumerate_itemsets(txns, max_length);
    let ts_fin = txns.last().map(|t| t.ts).unwrap_or(0);

    let evaluated: Vec<(String, usize, Value)> = counts
        .into_par_iter()
        .filter_map(|(itemset, sup)| {
            if sup < minsup {
                return None;
            }
            let mut tss = ts_map.get(&itemset).cloned().unwrap_or_default();
            tss.sort_unstable();
            let ps = periods(&tss, ts_fin);
            if ps.is_empty() {
                return None;
            }
            let pmin = *ps.iter().min().unwrap_or(&0);
            let pmax = *ps.iter().max().unwrap_or(&0);
            let pavg = ps.iter().sum::<i64>() as f64 / ps.len() as f64;
            if pmin >= min_per && pmax <= max_per && pavg >= min_avg && pavg <= max_avg {
                let k = key_of(&itemset);
                Some((k, sup, json!({"minPer": pmin, "maxPer": pmax, "avgPer": pavg})))
            } else {
                None
            }
        })
        .collect();

    let mut patterns = HashMap::new();
    let mut stat = serde_json::Map::new();
    for (k, sup, v) in evaluated {
        patterns.insert(k.clone(), sup);
        stat.insert(k, v);
    }

    RustOutput {
        method: "pfpm".to_string(),
        patterns,
        intervals: HashMap::new(),
        metadata: json!({"impl": "rust_pfpm", "periodicity": stat, "minsup_count": minsup}),
    }
}

fn solve_ppfpm(txns: &[Txn], params: &Value) -> RustOutput {
    let max_length = params
        .get("max_length")
        .and_then(|x| x.as_u64())
        .unwrap_or(4) as usize;
    let minsup = minsup_count(params, txns.len());
    let max_per = params
        .get("maxPer")
        .and_then(|x| x.as_i64())
        .unwrap_or(i64::MAX / 4);
    let min_pr = params.get("minPR").and_then(|x| x.as_f64()).unwrap_or(0.0);

    let (counts, ts_map) = enumerate_itemsets(txns, max_length);
    let ts_fin = txns.last().map(|t| t.ts).unwrap_or(0);

    let evaluated: Vec<(String, usize, f64)> = counts
        .into_par_iter()
        .filter_map(|(itemset, sup)| {
            if sup < minsup {
                return None;
            }
            let mut tss = ts_map.get(&itemset).cloned().unwrap_or_default();
            tss.sort_unstable();
            let ps = periods(&tss, ts_fin);
            if ps.is_empty() {
                return None;
            }
            let ip = ps.iter().filter(|x| **x <= max_per).count() as f64;
            let pr = ip / ps.len() as f64;
            if pr >= min_pr {
                Some((key_of(&itemset), sup, pr))
            } else {
                None
            }
        })
        .collect();

    let mut patterns = HashMap::new();
    let mut prs = serde_json::Map::new();
    for (k, sup, pr) in evaluated {
        patterns.insert(k.clone(), sup);
        prs.insert(k, json!(pr));
    }

    RustOutput {
        method: "ppfpm_gpf_growth".to_string(),
        patterns,
        intervals: HashMap::new(),
        metadata: json!({"impl": "rust_ppfpm", "periodic_ratio": prs, "minsup_count": minsup}),
    }
}

fn solve_lpfim(txns: &[Txn], params: &Value) -> RustOutput {
    let max_length = params
        .get("max_length")
        .and_then(|x| x.as_u64())
        .unwrap_or(4) as usize;
    let sigma = params
        .get("sigma")
        .and_then(|x| x.as_u64())
        .unwrap_or(minsup_count(params, txns.len()) as u64) as usize;
    let minthd1 = params.get("minthd1").and_then(|x| x.as_i64()).unwrap_or(1);
    let minthd2 = params.get("minthd2").and_then(|x| x.as_i64()).unwrap_or(0);

    let (counts, ts_map) = enumerate_itemsets(txns, max_length);

    let evaluated: Vec<(String, usize, Vec<[i64; 2]>)> = counts
        .into_par_iter()
        .filter_map(|(itemset, cnt)| {
            if cnt < sigma {
                return None;
            }
            let mut tss = ts_map.get(&itemset).cloned().unwrap_or_default();
            tss.sort_unstable();
            if tss.is_empty() {
                return None;
            }
            let mut out = Vec::new();
            let mut st = tss[0];
            let mut ed = tss[0];
            let mut c = 1usize;

            for ts in tss.iter().skip(1) {
                if *ts - ed < minthd1 {
                    ed = *ts;
                    c += 1;
                } else {
                    if (ed - st) >= minthd2 && c >= sigma {
                        out.push([st, ed]);
                    }
                    st = *ts;
                    ed = *ts;
                    c = 1;
                }
            }
            if (ed - st) >= minthd2 && c >= sigma {
                out.push([st, ed]);
            }

            if out.is_empty() {
                None
            } else {
                Some((key_of(&itemset), cnt, out))
            }
        })
        .collect();

    let mut patterns = HashMap::new();
    let mut intervals: HashMap<String, Vec<[i64; 2]>> = HashMap::new();
    for (k, cnt, out) in evaluated {
        patterns.insert(k.clone(), cnt);
        intervals.insert(k, out);
    }

    RustOutput {
        method: "lpfim".to_string(),
        patterns,
        intervals,
        metadata: json!({"impl": "rust_lpfim", "decision": "support_count_based", "sigma": sigma}),
    }
}

fn solve_lppm(txns: &[Txn], params: &Value) -> RustOutput {
    let max_length = params
        .get("max_length")
        .and_then(|x| x.as_u64())
        .unwrap_or(4) as usize;
    let max_per = params.get("maxPer").and_then(|x| x.as_i64()).unwrap_or(10);
    let max_so_per = params.get("maxSoPer").and_then(|x| x.as_i64()).unwrap_or(0);
    let min_dur = params.get("minDur").and_then(|x| x.as_i64()).unwrap_or(1);

    let (counts, ts_map) = enumerate_itemsets(txns, max_length);
    let evaluated: Vec<(String, usize, Vec<[i64; 2]>)> = ts_map
        .into_par_iter()
        .filter_map(|(itemset, mut tss)| {
            tss.sort_unstable();
            if tss.len() < 2 {
                return None;
            }
            let mut st = tss[0];
            let mut prev = tss[0];
            let mut so = 0i64;
            let mut ivals: Vec<[i64; 2]> = Vec::new();

            for ts in tss.iter().skip(1) {
                let gap = *ts - prev;
                if gap > max_per {
                    so += gap - max_per;
                }
                if so > max_so_per {
                    if (prev - st) >= min_dur {
                        ivals.push([st, prev]);
                    }
                    st = *ts;
                    so = 0;
                }
                prev = *ts;
            }

            if (prev - st) >= min_dur {
                ivals.push([st, prev]);
            }

            if ivals.is_empty() {
                None
            } else {
                Some((
                    key_of(&itemset),
                    *counts.get(&itemset).unwrap_or(&0),
                    ivals,
                ))
            }
        })
        .collect();

    let mut patterns = HashMap::new();
    let mut intervals: HashMap<String, Vec<[i64; 2]>> = HashMap::new();
    for (k, sup, ivals) in evaluated {
        patterns.insert(k.clone(), sup);
        intervals.insert(k, ivals);
    }

    RustOutput {
        method: "lppm".to_string(),
        patterns,
        intervals,
        metadata: json!({"impl": "rust_lppm", "maxPer": max_per, "maxSoPer": max_so_per, "minDur": min_dur}),
    }
}

fn main() {
    let cli = match parse_args() {
        Ok(v) => v,
        Err(e) => {
            eprintln!("arg error: {e}");
            std::process::exit(2);
        }
    };

    let params: Value = serde_json::from_str(&cli.params_json).unwrap_or_else(|_| json!({}));

    let txns = match parse_input(&cli.input, &cli.input_format) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("input parse error: {e}");
            std::process::exit(2);
        }
    };

    let out = match cli.method.as_str() {
        "apriori" | "fp_growth" | "eclat" | "lcm" => {
            solve_pattern_family(cli.method.as_str(), &txns, &params)
        }
        "pfpm" => solve_pfpm(&txns, &params),
        "ppfpm_gpf_growth" => solve_ppfpm(&txns, &params),
        "lpfim" => solve_lpfim(&txns, &params),
        "lppm" => solve_lppm(&txns, &params),
        _ => {
            eprintln!("unknown method={}", cli.method);
            std::process::exit(2);
        }
    };

    println!("{}", serde_json::to_string(&out).unwrap_or_else(|_| "{}".to_string()));
}
