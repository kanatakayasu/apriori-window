# Skill: debug-test

## 0. Purpose

- **このSkillが解くタスク**: Rust / Python テスト失敗の原因特定と修正
- **使う場面**: `cargo test` または `pytest` が失敗したとき / CI が落ちたとき / 新機能追加後にリグレッションが発生したとき
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

まず Rust と Python のどちらが落ちているかを切り分ける:

```sh
# Rust（apriori_window_suite/ 内から）
cd apriori_window_suite && cargo test 2>&1 | grep -E "FAILED|error"

# Python（リポジトリルートから）
python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | grep -E "FAILED|ERROR"
```

### 3.2 エラータイプの分類と対処方針

| エラータイプ | 見分け方 | 最初に疑う場所 |
|-------------|---------|--------------|
| **コンパイルエラー** | `cargo test` が `error[E...]` で止まる | 変更した `.rs` ファイルの型・所有権 |
| **Rust パニック** | `thread 'test_xxx' panicked at` | `src/*.rs` の当該関数・境界値処理 |
| **Rust アサーション失敗** | `assertion failed: ...` / `left: ... right: ...` | 期待値と実際の値の差を確認 |
| **Python ImportError** | `ModuleNotFoundError` / `ImportError` | `sys.path` 設定・ファイル名のタイポ |
| **Python アサーション失敗** | `AssertionError` / `assert ... == ...` | 該当テストの期待値と実装の差 |
| **Python 型エラー** | `TypeError` / `AttributeError` | 変更した関数のシグネチャ・戻り値型 |

### 3.3 Rust テスト失敗のデバッグ手順

1. **失敗テスト名の特定**:
   ```sh
   cd apriori_window_suite && cargo test 2>&1 | grep "FAILED"
   ```
2. **該当テストだけ実行して詳細出力を得る**:
   ```sh
   cd apriori_window_suite && cargo test test_xxx -- --nocapture
   ```
3. **ソースの読み取り**: 失敗した `#[test]` 関数を `Read` で確認する
4. **型・所有権エラーの場合**: `LSP` の `hover` / `goToDefinition` で型情報を確認する
5. **アサーション失敗の場合**: 期待値と実測値のどちらが正しいかを仕様（`doc/`）と照合する

よくある Rust の失敗パターン:

```
// スタックケースが発火してループが終わらない（interval.rs）
// → window_occurrences[surplus] の条件を確認する

// pub use 漏れで関数が外から見えない（lib.rs）
// → lib.rs の pub use チェーンに追加されているか確認する

// rayon の par_iter でクローン不足
// → par_iter().map(|x| x.clone()) を検討する
```

### 3.4 Python テスト失敗のデバッグ手順

1. **失敗テスト名の特定**:
   ```sh
   python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | grep "FAILED"
   ```
2. **該当テストだけ実行して詳細出力を得る**:
   ```sh
   python3 -m pytest apriori_window_suite/python/tests/test_basket.py::TestClass::test_xxx -v -s
   ```
3. **ImportError が出た場合**:
   - `test_basket.py` 冒頭の `sys.path.insert(0, parents[1])` が `python/` を指しているか確認
   - `event_correlator.py` 冒頭の `sys.path.insert(0, parent)` が正しいか確認
4. **アサーション失敗の場合**: 期待値を `doc/` の仕様と照合し、実装側かテスト側のどちらがずれているかを判断する

よくある Python の失敗パターン:

```python
# sys.path が正しく設定されていない
# → tests/ から見た python/ のパスを確認

# event_correlator.py が apriori_window_basket をインポートできない
# → parent = Path(__file__).parent.parent が python/ を指しているか確認

# 時間的関係の境界値（epsilon, d_0）の解釈がずれている
# → doc/phase2_impl_plan.md の条件式と照合する
```

### 3.5 Python と Rust の出力が一致しない場合

両方のテストは通るが出力が微妙にずれる場合:

```sh
# Rust 実行
cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json

# Python 実行
python3 apriori_window_suite/python/event_correlator.py apriori_window_suite/data/settings_phase2.json

# 差分確認（ソートして比較）
diff <(sort apriori_window_suite/data/output/relations.csv) <(sort /tmp/py_relations.csv)
```

ずれる原因と対策:

| 原因 | 対策 |
|------|------|
| ソート順の違い | 両実装で同じキーでソートする |
| 浮動小数点の比較 | 整数演算のみを使う（小数を避ける） |
| 空集合・単体の扱いの違い | `len == 1` のスキップ処理を両側で確認する |

---

## 4. Quality Gates

- **テスト件数の下限維持**: Rust 54+、Python Phase 1 24+、Python Phase 2 40+ を維持していること
- **修正の最小性**: テスト失敗に直接関係しない箇所を変更していないこと
- **全テスト通過**: 特定テストを fix した後、`cargo test` と `pytest` の全テストが passed であること
- **スタックケースの保護**: `interval.rs` / `interval.py` を変更した場合、`test_no_infinite_loop` 相当のテストが passed であること

---

## 5. Failure Modes & Fixes

- **失敗例1: 推測で修正して別のテストを壊す** / 原因: エラー出力を読まずに変更 / 回避策: 必ずエラー全文を読んでから修正箇所を決める
- **失敗例2: Python の ImportError を解消できない** / 原因: sys.path の設定ミス / 回避策: `Read` で tests ファイルの先頭 10 行を確認し、`parents[1]` が `python/` を指しているか確認する
- **失敗例3: アサーション失敗の原因を誤判断（実装側ではなくテスト側が間違っていた）** / 原因: 仕様照合を省略 / 回避策: `doc/phase1_impl_plan.md` / `doc/phase2_impl_plan.md` を必ず参照してから判断する
- **失敗例4: 1 テストを直したら別のテストが落ちた** / 原因: 共有ロジックを変更した副作用 / 回避策: 修正後に `cargo test` と `pytest` を両方フル実行する
- **失敗例5: Rust コンパイルエラーが解消しない** / 原因: 型・ライフタイムの理解不足 / 回避策: `LSP` の `hover` で型情報を確認し、`goToDefinition` で定義元を追う

---

## 6. Evaluation

- **合格ライン**: 失敗原因が特定され、最小差分で修正され、全テストが passed
- **重大欠陥（即NG）**:
  - 失敗テストを削除して「テストを通した」とする
  - 件数下限（Rust 54 / Python Phase 1 24 / Python Phase 2 40）を下回っている
  - 修正後に `cargo test` と `pytest` の両方を実行せずに完了とした

---

## 7. Execution Notes

- **テスト実行コマンド（フル）**:
  ```sh
  cd apriori_window_suite && cargo test
  python3 -m pytest apriori_window_suite/python/tests/ -v
  ```
- **特定テストのみ実行（Rust）**:
  ```sh
  cd apriori_window_suite && cargo test <テスト名> -- --nocapture
  cd apriori_window_suite && cargo test interval    # モジュール名でフィルタ
  ```
- **特定テストのみ実行（Python）**:
  ```sh
  python3 -m pytest apriori_window_suite/python/tests/test_basket.py -v -s
  python3 -m pytest apriori_window_suite/python/tests/test_basket.py::TestClass::test_xxx -v -s
  ```
- **参照すべき仕様ファイル**:
  - `apriori_window_suite/doc/phase1_impl_plan.md` — Phase 1 のアルゴリズム仕様
  - `apriori_window_suite/doc/phase2_impl_plan.md` — Phase 2 の時間的関係条件式
  - `apriori_window_suite/src/interval.rs` — スタックケースの実装参照
