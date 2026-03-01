# CLAUDE.md — apriori_window

## 0. Repository Purpose

- **目的**: バスケット構造対応 Apriori + スライディングウィンドウで密集アイテムセット区間を検出し、外部イベントとの時間的関係を列挙する
- **主要成果物**: `apriori_window_suite/` クレート（Rust + Python 二重実装）
- **現在のフェーズ**: Phase 1・Phase 2 完了 → Phase 3（実データ検証）着手前

---

## 1. Directory Layout

```
apriori_window/
  CLAUDE.md                        ← このファイル
  skills/                          ← タスク手順書（Skill）
  dataset/                         ← 実験データセット置き場（Phase 3 用）
  apriori_window_suite/            ← メイン実装クレート（スタンドアロン Rust crate）
    Cargo.toml                     ← クレートマニフェスト
    src/                           ← Rust 実装（lib.rs + main.rs + *.rs）
    python/                        ← Python 実装（apriori_window_basket.py, event_correlator.py）
    python/tests/                  ← pytest テスト（test_basket.py, test_correlator.py）
    data/                          ← サンプルデータ・settings.json
    doc/                           ← 設計書・README（impl_plan.md, phase1/2_impl_plan.md 等）
  apriori_window_original/         ← バスケットなし版リファレンス（独立クレート）
```

---

## 2. Working Principles

- **Python → Rust の二段構成を守る**: 機能追加は必ず Python プロトタイプで検証してから Rust に移植する
- **テストを壊さない**: 変更前後で `cargo test` と `pytest` が全 passed であること
- **最小差分の原則**: 要求された変更のみ行い、関係のないコードには触れない
- **impl_log.md を更新する**: 実装完了後は `apriori_window_suite/doc/impl_log.md` に追記する
- **推測で進めない**: アルゴリズムの挙動や仕様が不明な場合は質問するか「不明」と明示する
- **APIキー・認証情報をコミットしない**

---

## 3. Commands

### テスト

```sh
# Rust（全テスト）— apriori_window_suite/ 内から実行
cd apriori_window_suite && cargo test

# Python（全テスト）— リポジトリルートから実行可能
python3 -m pytest apriori_window_suite/python/tests/ -v

# 特定モジュールのみ
cd apriori_window_suite && cargo test interval
python3 -m pytest apriori_window_suite/python/tests/test_basket.py -v
```

### 実行

```sh
# Phase 1（デフォルト設定）— apriori_window_suite/ 内から
cd apriori_window_suite && cargo run -- phase1

# Phase 2（設定ファイル指定）
cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json

# Python Phase 1
python3 apriori_window_suite/python/apriori_window_basket.py [settings.json]

# Python Phase 2
python3 apriori_window_suite/python/event_correlator.py [settings.json]
```

### ビルド

```sh
cd apriori_window_suite && cargo build --release
```

---

## 4. Key Design Constraints

| 制約 | 内容 |
|------|------|
| 共起定義 | 同一**バスケット**内（トランザクションではない） |
| スタックケース | `window_occurrences[surplus] == l` のとき `l += 1`（`interval.rs` / `interval.py`） |
| 単体アイテム出力 | `write_patterns_csv` では len==1 はスキップ |
| import 依存 | `io.rs` → `correlator.rs` の一方向のみ（逆は禁止） |
| Python パス | `event_correlator.py` は `sys.path.insert(0, parent)` でバスケットモジュールを import |
| 時間的関係 | 6種: DFE / EFD / DCE / ECD / DOE / EOD（詳細は `doc/phase2_impl_plan.md`） |

---

## 5. Git / PR Workflow

- **作業ブランチ**: `dev_new_model`（現在）、新機能は `feature/<name>` を切る
- **マージ先**: `main`
- **コミット粒度**: 1コミット1意図（Python prototype / Rust port / test add / doc update は別コミット）
- **PR に書くこと**: 変更点 / テスト結果（passed件数）/ 影響範囲

---

## 6. Skills

| Skill | 使う場面 |
|-------|---------|
| [`skills/impl-feature.md`](./skills/impl-feature.md) | 新しいアルゴリズム機能の追加（Python prototype → Rust port） |
| [`skills/run-experiment.md`](./skills/run-experiment.md) | 実データセットでの実験実行と結果記録（Phase 3） |
| [`skills/update-docs.md`](./skills/update-docs.md) | コード変更後のドキュメント整合性確認・更新 |

---

## 7. Test Baseline

変更前後でこの件数を下回ったら問題：

| 対象 | 件数 |
|------|------|
| Rust lib テスト | 54 |
| Rust main（E2E）テスト | 4 |
| Python Phase 1 pytest | 24 |
| Python Phase 2 pytest | 40 |
