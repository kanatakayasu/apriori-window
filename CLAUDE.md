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
  AGENTS.md                        ← エージェント役割定義（AI-native構造）
  .agents/skills/                  ← タスク手順書（Skill）— `/skill-name` で呼び出し可能
  .claude/commands/                ← カスタムスラッシュコマンド（/run-experiment 等）
  dataset/                         ← 実験データセット置き場（Phase 3 用）
  apriori_window_suite/            ← メイン実装クレート（スタンドアロン Rust crate）
    Cargo.toml                     ← クレートマニフェスト
    src/                           ← Rust 実装（lib.rs + main.rs + *.rs）
    python/                        ← Python 実装（apriori_window_basket.py, event_correlator.py）
    python/tests/                  ← pytest テスト（test_basket.py, test_correlator.py）
    data/                          ← サンプルデータ・settings.json
    doc/                           ← 設計書・README（impl_plan.md, phase1/2_impl_plan.md 等）
  apriori_window_original/         ← バスケットなし版リファレンス（独立クレート）
  baselines/                       ← 比較手法（旧 comparative_methods/）
    methods/                       ← 各手法のドキュメント（lpfim.md, eclat.md 等）
    research/                      ← 調査レポート
    runner/                        ← 手法実行ランナー（registry.py, run_method.py 等）
    specs/                         ← I/O 仕様・ソース調査
    adapters/                      ← 統一 I/O に揃える薄いラッパ（新規）
    external/                      ← 外部実装（git submodule 推奨）
    patches/                       ← 外部実装への差分（パッチ管理）
  benchmarks/                      ← ベンチマーク定義（スイート・データセット・指標・プロトコル）
    suites/                        ← 実験セット定義（main.yaml, ablation.yaml 等）
    datasets/                      ← データセットメタ情報（synthetic.yaml 等）
    metrics/                       ← 指標定義（definitions.md, compute.py）
    protocol/                      ← 評価プロトコル（io_spec.md, timing.md, seeds.md）
  experiments/                     ← 実験実行入口・結果索引
    configs/                       ← 個別実験条件（exp001_*.yaml 等）
    registry/                      ← 実験台帳（experiments.csv, schema.md）
    reports/                       ← 集計結果（tables/, figures/）
    results/                       ← 実験生データ（gitignore 外 CSV 等）
    doc/                           ← 実験設計書
  runs/                            ← 実行結果生データ（.gitignore 対象・大容量）
  paper/                           ← カンファレンス提出物・論文全般
    manuscript/                    ← LaTeX 原稿（旧 paper_basket/）
    target/dsaa2025/               ← DSAA2025 提出物（旧 DSAA2025/）
    target/main_manuscript/        ← メイン原稿への案内 README
    bibliography/                  ← 文献管理
    reproducibility_appendix/      ← 再現性情報（environment.md 等）
  tools/                           ← 開発補助スクリプト・プロンプト資産
    scripts/                       ← format.sh, lint.sh, gen_figs.py 等
    prompts/                       ← 文章生成用プロンプト
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

- **作業ブランチ**: `dev_takayasu`（現在）、新機能は `feature/<name>` を切る
- **マージ先**: `main`
- **コミット粒度**: 1コミット1意図（Python prototype / Rust port / test add / doc update は別コミット）
- **PR に書くこと**: 変更点 / テスト結果（passed件数）/ 影響範囲

---

## 6. Skills

スキルは `.agents/skills/` で管理。`/skill-name` 形式で呼び出し可能。

**リポジトリ固有スキル**（`.agents/skills/` 配下）:

| Skill | 使う場面 |
|-------|---------|
| `impl-feature` | 新しいアルゴリズム機能の追加（Python prototype → Rust port） |
| `run-experiment` | 実データセットでの実験実行と結果記録（Phase 3） |
| `update-docs` | コード変更後のドキュメント整合性確認・更新 |
| `git-workflow` | コミット分割・PR 作成・push 前チェック |
| `debug-test` | Rust / Python テスト失敗の原因特定と修正 |
| `write-paper` | Phase 1 拡張論文の執筆・改訂（構成・各セクションの書き方・LaTeX ルール） |

**マーケットプレイス スキル**（`.agents/skills/` 配下）:

| Skill | 使う場面 |
|-------|---------|
| `rust-best-practices` | Rust コードの品質・パターン確認（Apollo GraphQL） |
| `python-testing-patterns` | pytest パターン・テスト設計のベストプラクティス |
| `git-advanced-workflows` | 高度な git 操作（rebase・cherry-pick 等） |
| `ml-paper-writing` | ML 系論文の一般的な執筆ガイド（ICLR/ICML/NeurIPS テンプレート付き） |

---

## 7. Test Baseline

変更前後でこの件数を下回ったら問題：

| 対象 | 件数 |
|------|------|
| Rust lib テスト | 54 |
| Rust main（E2E）テスト | 4 |
| Python Phase 1 pytest | 24 |
| Python Phase 2 pytest | 40 |
