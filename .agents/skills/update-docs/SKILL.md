---
name: update-docs
description: コード変更後にドキュメントを最新状態に同期させる。テスト件数・パラメータ・出力形式・ファイル構成などの整合性維持に使う。
---

# Skill: update-docs

## 0. Purpose

- **このSkillが解くタスク**: コード変更後にドキュメントを最新状態に同期させる（テスト件数・パラメータ・出力形式・ファイル構成などの整合性維持）
- **使う場面**: 新機能追加後 / バグ修正後 / テスト件数が変わった後 / パラメータ追加・削除 / ディレクトリ構成の変更後
- **できないこと（スコープ外）**: アルゴリズム設計書の新規作成・スライドや画像ファイルの更新・テスト自体の修正

---

## 1. Inputs

### 1.1 Required

- **変更内容の概要**: 何を変更したか（機能追加 / バグ修正 / パラメータ変更 など）
- **変更ファイル**: 実際に変更した `.rs` / `.py` / `Cargo.toml` のパス

### 1.2 Optional

- **変更前後のテスト件数**: `cargo test` / `pytest` の件数（省略時は自分で確認する）
- **新しいパラメータ仕様**: 追加・削除されたパラメータの名前・型・デフォルト値
- **出力形式の変更点**: CSV のカラム名変更・追加・削除

### 1.3 Missing info policy

- 変更内容が不明な場合は `git diff HEAD~1` か変更ファイルの `Read` で自力確認する
- テスト件数が不明な場合はコマンドを実行して取得する（推測で書かない）

---

## 2. Outputs

### 2.1 Deliverables

- **`CLAUDE.md`（Section 7: Test Baseline）**: テスト件数の更新
- **`apriori_window_suite/doc/README.md`**: テスト件数テーブル・パラメータ表・出力形式・ファイル構成のうち変更に関係する箇所
- **`apriori_window_suite/doc/impl_log.md`**: 今回の変更を 1 エントリとして追記

### 2.2 impl_log.md エントリ形式

```markdown
## YYYY-MM-DD — <変更の要点 1 行>

- 変更ファイル: `<path>`, `<path>` …
- Rust テスト: N passed（前回 N）
- Python テスト: N passed（前回 N）
- 変更点: （箇条書きで 3〜5 行）
- 備考: （影響範囲・既知の制限など）
```

---

## 3. Procedure

1. **変更内容の把握**: `git diff HEAD~1 -- <changed_file>`
2. **テスト件数の取得**:
   ```sh
   cd apriori_window_suite && cargo test 2>&1 | grep "test result"
   python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | tail -5
   ```
3. **影響するドキュメントの特定**:

   | 変更の種類 | 更新が必要なドキュメント箇所 |
   |-----------|--------------------------|
   | Rust テスト件数の増減 | CLAUDE.md § 7 / README.md テストケース概要テーブル |
   | Python テスト件数の増減 | CLAUDE.md § 7 / README.md テストケース概要テーブル |
   | パラメータ追加・削除 | README.md パラメータ表 / settings.json 例 |
   | CSV カラム変更 | README.md 出力形式セクション |
   | ファイル追加・削除 | CLAUDE.md § 1 ディレクトリレイアウト / README.md ファイル構成 |
   | 時間的関係の変更 | README.md 時間的関係テーブル / phase2_impl_plan.md |

4. **CLAUDE.md の更新**: `## 7. Test Baseline` の件数を実測値に書き換える
5. **README.md の更新**: 手順 3 で特定した箇所のみを最小差分で更新する
6. **impl_log.md への追記**: 上記の形式でエントリを追加する

---

## 4. Quality Gates

- **テスト件数の一致**: `CLAUDE.md § 7` の数値と `cargo test` / `pytest` の実出力が一致すること
- **README.md テーブルの整合**: テストケース概要テーブルの件数が実際のテスト実行結果と一致すること
- **ファイル構成の正確性**: CLAUDE.md § 1 のレイアウトと実際の `ls apriori_window_suite/` が一致すること
- **impl_log.md の更新**: 今回の変更エントリが追記されていること
- **最小差分の原則**: 変更に関係しない箇所を書き換えていないこと

---

## 5. Failure Modes & Fixes

- **失敗例1: テスト件数を推測で記入** / 回避策: 必ずコマンドを実行し `test result: ok. N passed` の N を直接使う
- **失敗例2: CLAUDE.md と README.md の数値が食い違う** / 回避策: 両ファイルをセットで更新する
- **失敗例3: 実在しないファイルをレイアウト図に記載** / 回避策: `Glob` で実ファイルを確認してから記述する
- **失敗例4: 変更に関係しない文章を整理・改変してしまう** / 回避策: diff が小さいほど良い

---

## 7. Execution Notes

- **主な更新対象ファイル**:
  - `CLAUDE.md` — Section 7 (Test Baseline)
  - `apriori_window_suite/doc/README.md` — テストケース概要テーブル / パラメータ表 / 出力形式 / ファイル構成
  - `apriori_window_suite/doc/impl_log.md` — 追記（なければ新規作成）
- **テスト実行コマンド**:
  ```sh
  cd apriori_window_suite && cargo test 2>&1 | grep "test result"
  python3 -m pytest apriori_window_suite/python/tests/ -v 2>&1 | tail -5
  ```
