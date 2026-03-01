use std::env;
use std::path::PathBuf;
use std::time::Instant;

use new_apriori_window::{find_dense_itemsets, read_text_file_as_2d_vec_of_integers, write_output_csv};
use serde::Deserialize;

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

fn main() {
    let default_settings =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("data").join("settings.json");
    let settings_path = env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or(default_settings);

    let settings_text =
        std::fs::read_to_string(&settings_path).expect("failed to read settings.json");
    let settings: Settings =
        serde_json::from_str(&settings_text).expect("failed to parse settings.json");

    let input_path = PathBuf::from(&settings.input_file.dir).join(&settings.input_file.file_name);
    let window_size = settings.apriori_parameters.window_size as i64;
    let threshold = settings.apriori_parameters.min_support;
    let max_length = settings.apriori_parameters.max_length;
    let output_dir = settings.output_files.dir;
    let output_file_name = settings.output_files.patterns_output_file_name;

    let start = Instant::now();
    let transactions = read_text_file_as_2d_vec_of_integers(input_path.to_str().unwrap());
    let frequents = find_dense_itemsets(&transactions, window_size, threshold, max_length);

    let out_path = PathBuf::from(output_dir).join(output_file_name);
    write_output_csv(&out_path, &frequents).expect("failed to write output");
    println!("Wrote output to {}.", out_path.display());
    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    println!("Elapsed time: {:.3} ms", elapsed_ms);
}
