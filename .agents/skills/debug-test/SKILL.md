---
name: debug-test
description: Rust / Python テスト失敗の原因特定と修正。cargo test または pytest が失敗したとき / CI が落ちたとき / 新機能追加後にリグレッションが発生したときに使う。
---

# Skill: debug-test

## 0. Purpose

- **このSkillが解くタスク**: Rust / Python テスト失敗の原因特定と修正
- **使う場面**: `cargo test` または `pytest` が失敗したとき / CI が落ちたとき / リグレッション発生時
- **できないこと（スコープ外）**: テスト設計の根本的な変更・アルゴリズムの再設計

---

## 1. Inputs

### 1.1 Required

- **失敗したテストの出力**: エラーメッセージ全文（`cargo test -- --nocapture` または `pytest -v` の出力）
- **どちらが失敗したか**: Rust / Python Phase 1 / Python Phase 2 のいずれか（または複数）

### 1.2 Optional

- **直前の変更内容**: 何を変更した後に失敗が起きたか
- **失敗しているテスト名**: 特定のテストだけ失敗している場合

### 1.3 Missing info policy

- エラー出力が省略されている場合は全文を取得してから判断する（推測で修正しない）
- 失敗の再現が取れない場合は環境差異（Python バージョン・Rust ツールチェーン）を先に確認する

---

## 2. Outputs

### 2.1 Deliverables

- **原因の特定**: どのファイルの何行目が問題か
- **修正差分**: 最小限の変更のみ（関係ない箇所は触らない）
- **修正後のテスト結果**: 全テスト passed であることの確認

---

## 3. Procedure

### 3.1 失敗の範囲を絞る

```sh
# Rust
cd apriori_window_suite && cargo test 2>&1 | grep -E "FAILED|error"
# Python
python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | grep -E "FAILED|ERROR"
```

### 3.2 エラータイプの分類と対処方針

| エラータイプ | 見分け方 | 最初に疑う場所 |
|-------------|---------|--------------|
| **コンパイルエラー** | `cargo test` が `error[E...]` で止まる | 変更した `.rs` ファイルの型・所有権 |
| **Rust パニック** | `thread 'test_xxx' panicked at` | `src/*.rs` の当該関数・境界値処理 |
| **Rust アサーション失敗** | `assertion failed:` / `left: ... right: ...` | 期待値と実際の値の差を確認 |
| **Python ImportError** | `ModuleNotFoundError` / `ImportError` | `sys.path` 設定・ファイル名のタイポ |
| **Python アサーション失敗** | `AssertionError` | 該当テストの期待値と実装の差 |

### 3.3 Rust テスト失敗のデバッグ手順

1. `cd apriori_window_suite && cargo test 2>&1 | grep "FAILED"`
2. `cd apriori_window_suite && cargo test test_xxx -- --nocapture`
3. ソースを `Read` で確認し、`LSP` の `hover` / `goToDefinition` で型情報を確認する
4. 期待値と実測値のどちらが正しいかを仕様（`doc/`）と照合する

よくある Rust の失敗パターン:
- スタックケースが発火してループが終わらない（`interval.rs`）→ `window_occurrences[surplus]` の条件を確認
- `pub use` 漏れで関数が外から見えない（`lib.rs`）→ `lib.rs` の pub use チェーンに追加されているか確認
- `rayon` の `par_iter` でクローン不足 → `par_iter().map(|x| x.clone())` を検討

### 3.4 Python テスト失敗のデバッグ手順

1. `python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | grep "FAILED"`
2. `python3 -m pytest apriori_window_suite/python/tests/test_basket.py::TestClass::test_xxx -v -s`
3. `ImportError` が出た場合: `sys.path.insert(0, parents[1])` が `python/` を指しているか確認
4. アサーション失敗: `doc/` の仕様と照合し、実装側かテスト側のどちらがずれているかを判断する

### 3.5 Python と Rust の出力が一致しない場合

```sh
cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json
python3 apriori_window_suite/python/event_correlator.py apriori_window_suite/data/settings_phase2.json
diff <(sort apriori_window_suite/data/output/relations.csv) <(sort /tmp/py_relations.csv)
```

| 原因 | 対策 |
|------|------|
| ソート順の違い | 両実装で同じキーでソートする |
| 浮動小数点の比較 | 整数演算のみを使う |
| 空集合・単体の扱いの違い | `len == 1` のスキップ処理を両側で確認する |

---

## 4. Quality Gates

- **テスト件数の下限維持**: Rust 54+、Python Phase 1 24+、Python Phase 2 40+ を維持していること
- **修正の最小性**: テスト失敗に直接関係しない箇所を変更していないこと
- **全テスト通過**: `cargo test` と `pytest` の全テストが passed であること
- **スタックケースの保護**: `interval.rs` / `interval.py` を変更した場合、`test_no_infinite_loop` 相当が passed であること

---

## 5. Failure Modes & Fixes

- **失敗例1: 推測で修正して別のテストを壊す** / 回避策: エラー全文を読んでから修正箇所を決める
- **失敗例2: Python の ImportError を解消できない** / 回避策: `Read` で tests ファイルの先頭を確認し、`parents[1]` が `python/` を指しているか確認する
- **失敗例3: テストを削除して「テストを通した」とする** → 即NG

---

## 7. Execution Notes

- **参照すべき仕様ファイル**:
  - `apriori_window_suite/doc/phase1_impl_plan.md`
  - `apriori_window_suite/doc/phase2_impl_plan.md`
  - `apriori_window_suite/src/interval.rs`（スタックケースの実装参照）
