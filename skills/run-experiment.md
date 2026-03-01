# Skill: run-experiment

## 0. Purpose

- **このSkillが解くタスク**: 実データセットで apriori_window_suite を実行し、結果を記録・比較する（Phase 3）
- **使う場面**: 新しいデータセットでの初回実験 / パラメータ探索 / 複数設定の比較実験
- **できないこと（スコープ外）**: 統計的有意性検定・データセットのダウンロード・前処理スクリプトの作成

---

## 1. Inputs

### 1.1 Required

- **データセット**: `dataset/` 配下のトランザクションファイル（`.txt`）の名前
- **実験パラメータ**: `window_size`, `min_support`, `max_length`（必須）
- **実験の目的**: 何を確認したいか（例: min_support を変えて出力件数の変化を見る）

### 1.2 Optional

- **イベントファイル**: `data/` または `dataset/` 配下の `.json`（Phase 2 を実行する場合）
- **epsilon / d_0**: Phase 2 を実行する場合の時間的関係パラメータ
- **比較ベースライン**: 以前の実験結果ファイルのパス

### 1.3 Missing info policy

- データセットファイルが存在しない場合は、`dataset/` 配下を `Glob` で確認してから報告する
- パラメータが指定されていない場合は、デフォルト（`window_size=500, min_support=10, max_length=4`）を使い、その旨を明示する

---

## 2. Outputs

### 2.1 Deliverables

- **settings ファイル**: `dataset/<dataset_name>/settings_<params>.json`
- **出力 CSV**: `dataset/<dataset_name>/output/<params>/patterns.csv`（+ 必要なら `relations.csv`）
- **実験ログ**: `dataset/<dataset_name>/log.md` への追記

### 2.2 Structure

`log.md` の各エントリは以下の形式で追記する:

```markdown
## YYYY-MM-DD — <dataset_name> (window=N, minsup=N, maxlen=N)

- 実行時間: N ms（Rust）
- 検出パターン数: N件（要素数2以上）
- 密集区間総数: N件
- 備考: （注目すべき傾向・異常・次のアクション）
```

---

## 3. Procedure

1. **データ確認**: `dataset/` 配下のファイルを確認し、行数・アイテム数の概算をつかむ
   ```sh
   wc -l dataset/<name>.txt
   ```
2. **settings.json 作成**: `apriori_window_suite/data/settings_phase1.json` をテンプレートに、パスとパラメータを書き換えて `dataset/<name>/settings_<params>.json` に保存する
3. **出力ディレクトリ作成**: `dataset/<name>/output/<params>/` を確保する
4. **Rust で実行**（高速なので先に実施）:
   ```sh
   cd apriori_window_suite && cargo run --release -- phase1 /絶対パス/dataset/<name>/settings_<params>.json
   ```
5. **実行時間・件数を記録**: 標準出力の `Elapsed time` と CSV の行数を控える
   ```sh
   tail -n +2 dataset/<name>/output/<params>/patterns.csv | wc -l
   ```
6. **結果の妥当性確認**: 以下を目視で確認する
   - パターンが 0 件でないか（min_support が高すぎる可能性）
   - 異常に大きな件数でないか（min_support が低すぎる可能性）
   - 密集区間の start/end がデータの範囲内か
7. **Phase 2 を実行する場合**: イベントファイルと settings_phase2.json を用意して同様に実施する
8. **log.md に追記**: 手順2の形式で実験結果を記録する
9. **Python でのクロスチェック（任意）**: 大規模データでなければ Python でも実行して件数一致を確認する

---

## 4. Quality Gates

- **出力ファイルの存在**: `patterns.csv` が生成されており、ヘッダ行 + データ行が存在すること
- **パターン件数の妥当性**: 0 件または異常な件数（例: 10 万件超）の場合はパラメータを見直す
- **dense_intervals の範囲**: `start` が 0 以上、`end` がデータの最大トランザクション ID 以下であること
- **ログの記録**: `log.md` に今回の実験結果が追記されていること
- **settings.json の保存**: 再現可能なように settings ファイルが `dataset/` 配下に保存されていること
- **列名の一致**: CSV のヘッダが `pattern_components,pattern_gaps,pattern_size,intervals_count,intervals` の順であること

---

## 5. Failure Modes & Fixes

- **失敗例1: ファイルパスが見つからないエラー** / 原因: settings.json の `dir` が絶対パスでない / 回避策: `dir` には常に絶対パスを使用する
- **失敗例2: パターンが 0 件** / 原因: min_support が高すぎる / 回避策: min_support を半分にして再実行し、件数が増えることを確認する
- **失敗例3: 実行がタイムアウト** / 原因: min_support が低すぎて候補爆発 / 回避策: `--release` ビルドを使い、min_support を 2 倍にして再実行する
- **失敗例4: Python と Rust の件数が異なる** / 原因: ソートや境界条件の微差 / 回避策: 差分が 5% 未満なら許容し、大きければ `impl-feature` スキルでバグ修正を行う

---

## 6. Evaluation

- **合格ライン**: patterns.csv が生成され、件数が合理的な範囲（1〜10万件程度）にある + log.md に記録済み
- **重大欠陥（即NG）**:
  - patterns.csv が空（ヘッダのみ）
  - settings.json が `dataset/` 配下に保存されていない（再現不能）
  - dense_intervals の start > end

---

## 7. Execution Notes

- **参照ファイル**: `apriori_window_suite/data/settings_phase1.json`（テンプレート）
- **データ置き場**: `dataset/`（大きなファイルは `.gitignore` に追加すること）
- **実行コマンド**:
  ```sh
  # apriori_window_suite/ 内から実行（リリースビルド、実験には必ずこちらを使う）
  cd apriori_window_suite
  cargo build --release
  ./target/release/apriori_window_suite phase1 /絶対パス/dataset/<name>/settings_<params>.json
  ```
