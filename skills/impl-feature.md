# Skill: impl-feature

## 0. Purpose

- **このSkillが解くタスク**: apriori_window_suite への新しいアルゴリズム機能追加
- **使う場面**: 新しい時間的関係の追加 / 密集区間計算の改良 / 入出力形式の拡張 など
- **できないこと（スコープ外）**: データセットの前処理・有意性検定の実装・UI 構築

---

## 1. Inputs

### 1.1 Required

- **機能仕様**: 何を追加・変更するかの説明（自然文でよい）
- **影響モジュール**: どの `.rs` / `.py` ファイルを変更するか（不明なら調査フェーズで特定）

### 1.2 Optional

- 関連する設計書（`doc/phase1_impl_plan.md` / `doc/phase2_impl_plan.md`）
- 参照すべきテストケース（既存の類似テストがあれば）

### 1.3 Missing info policy

- 共起定義・スタックケース挙動など **アルゴリズムの意味論が不明な場合は作業を止めて質問する**
- 影響モジュールが不明な場合は `Grep` / `LSP` で調査してから着手する

---

## 2. Outputs

### 2.1 Deliverables

- 変更済みの Python ファイル（`python/apriori_window_basket.py` または `python/event_correlator.py`）
- 変更済みの Rust ファイル（`src/*.rs`）
- 追加テスト（既存ファイルへの追記 または 新規ファイル）
- `doc/impl_log.md` への追記

### 2.2 Structure

Python と Rust の変更は **必ず同じ動作** を実装する（動作差異は Quality Gate で検出）。
テストは `test_basket.py` / `test_correlator.py` の既存クラス構造に従って追加する。

---

## 3. Procedure

1. **仕様確認**: 何を・なぜ変更するかを明確化し、影響モジュールをリストアップする
2. **既存コードの精読**: 変更対象ファイルを `Read` + `LSP` で把握する（推測で編集しない）
3. **Python 実装**: `python/` 配下に実装し、インタープリタレベルで動作確認できる形にする
4. **Python テスト追加**: 新機能の正常系・境界値・異常系の各ケースを `test_*.py` に追記する
5. **Python テスト実行**: `python3 -m pytest apriori_window_suite/python/tests/ -v` が全 passed であることを確認する（リポジトリルートから実行）
6. **Rust 移植**: Python の実装を `src/*.rs` に同等ロジックで移植する
   - 型推論・所有権・並列化（rayon）に注意する
   - 既存の `pub use` チェーン（`lib.rs`）への追加が必要な場合は漏れなく行う
7. **Rust テスト追加**: 対応する `#[test]` を同ファイルの `mod tests` に追記する
8. **Rust テスト実行**: `cd apriori_window_suite && cargo test` が全 passed であることを確認する
9. **impl_log.md 更新**: 変更の要点・テスト件数・日付を `doc/impl_log.md` に追記する

---

## 4. Quality Gates

- **テスト件数の維持**: Rust 58+、Python 64+ を下回っていないこと
- **Python/Rust の動作一致**: 同一 settings.json で両方を実行し、`patterns.csv` / `relations.csv` の内容が一致すること
- **スタックケースの保護**: `compute_dense_intervals` を変更した場合、`test_no_infinite_loop` が引き続き passed であること
- **import 依存の方向**: `io.rs` → `correlator.rs` の一方向のみ（`correlator.rs` から `io.rs` を import しないこと）
- **単体アイテムのスキップ**: `write_patterns_csv` で len==1 のアイテムセットが出力されないこと
- **バスケット境界の正確性**: 別バスケットのアイテム間に共起が検出されないこと（`TestFalseCooccurrenceEliminated` 等価のテストが存在すること）

---

## 5. Failure Modes & Fixes

- **失敗例1: Rust の lifetime / 所有権エラー** / 原因: `Vec` のクローンが不足 / 回避策: `par_iter()` でエラーが出た場合は `par_iter().map(|x| x.clone())` を検討
- **失敗例2: Python と Rust の出力が微妙にずれる** / 原因: ソート順の違いや浮動小数点 / 回避策: 結果のソートキーを明示し、整数演算のみを使う
- **失敗例3: スタックケースが発火して無限ループ** / 原因: 新しいタイムスタンプ生成で重複を想定していない / 回避策: `window_occurrences[surplus] > l` の判定を必ず保持する
- **失敗例4: `lib.rs` の `pub use` 漏れ** / 原因: 新関数を追加したが外部から見えない / 回避策: `lib.rs` の pub use 一覧を毎回確認する

---

## 6. Evaluation

- **合格ライン**: Rust テスト全 passed + Python テスト全 passed + Python/Rust 出力一致
- **重大欠陥（即NG）**:
  - 既存テストが 1 件でも落ちている
  - `impl_log.md` が更新されていない
  - Python 実装のみで Rust 未移植のまま PR 提出

---

## 7. Execution Notes

- **参照すべきファイル**: `src/interval.rs`（スタックケース参照）、`src/correlator.rs`（関係判定ロジック参照）
- **テスト実行コマンド**:
  ```sh
  # Rust（apriori_window_suite/ 内から）
  cd apriori_window_suite && cargo test
  # Python（リポジトリルートから）
  python3 -m pytest apriori_window_suite/python/tests/ -v
  ```
- **出力確認コマンド**（Python/Rust 比較）:
  ```sh
  cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json
  python3 apriori_window_suite/python/event_correlator.py apriori_window_suite/data/settings_phase2.json
  diff <(sort apriori_window_suite/data/output/relations.csv) <(sort /tmp/py_relations.csv)
  ```
