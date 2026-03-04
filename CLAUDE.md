# CLAUDE.md — apriori_window

## 0. Repository Purpose

- **目的**: バスケット構造対応 Apriori + スライディングウィンドウで密集アイテムセット区間を検出し、外部イベントとの時間的関係を列挙する
- **主要成果物**: `apriori_window_suite/` クレート（Rust + Python 二重実装）
- **現在のフェーズ**: Phase 1・Phase 2 完了 → Phase 3（実データ検証）進行中

---

## 1. Directory Layout

```
apriori_window/
  README.md                        ← リポジトリ説明・クイックスタート
  CLAUDE.md                        ← このファイル（AI エージェント向けガイド）
  AGENTS.md                        ← エージェント役割定義
  .agents/skills/                  ← スキル定義（/skill-name で呼び出し）
  .claude/
    commands/                      ← カスタムスラッシュコマンド（/run-experiment 等）
    corrections.md                 ← 実装修正ログ（再発防止・ルール昇格の起点）
    settings.local.json            ← Claude Code 権限設定
  dataset/                         ← 実験データセット（一部 git 管理外）
    chicago.txt, kosarak.txt, retail.txt, onlineretail.txt
    dunnhumby/                     ← Dunnhumby データ（git 管理外）
  apriori_window_suite/            ← メイン実装クレート（Rust + Python）
    Cargo.toml
    src/                           ← Rust（lib.rs, main.rs, apriori.rs, basket.rs,
    │                                  correlator.rs, interval.rs, io.rs, util.rs）
    src/bin/comparative_mining.rs  ← 比較手法実行バイナリ
    python/
      apriori_window_basket.py     ← Phase 1 Python 実装
      event_correlator.py          ← Phase 2 Python 実装
      tests/test_basket.py         ← 24 件
      tests/test_correlator.py     ← 40 件
    data/                          ← サンプルデータ・settings*.json
    doc/
      OVERVIEW.md                  ← 実装詳細・API（旧 README.md）
      impl_log.md                  ← 実装変更履歴（実装後に追記）
      impl_plan.md, phase1/2_impl_plan.md
  apriori_window_original/         ← バスケットなし版リファレンス（workspace exclude）
  baselines/                       ← 比較手法（旧 comparative_methods/）
    OVERVIEW.md                    ← 手法一覧・入手元・注意点
    methods/                       ← 各手法のドキュメント（lpfim.md, eclat.md 等）
    runner/                        ← 手法実行ランナー（Python + Rust backend）
      run_method.py, registry.py, preprocess_inputs.py
      aggregate_stage_a.py, run_stage_a_suite.py
      adapters/                    ← SPMF/PAMI アダプタ
    research/                      ← 調査レポート（deep-research-report.md 等）
    specs/                         ← I/O 仕様・ソース調査
    results/                       ← スモーク実行結果
    adapters/                      ← 統一 I/O ラッパ（将来用・現在空）
    external/                      ← 外部実装置き場（git submodule 推奨）
    patches/                       ← 外部実装への差分
  benchmarks/                      ← ベンチマーク定義
    suites/main.yaml, ablation.yaml, scalability.yaml
    datasets/synthetic.yaml, dunnhumby.yaml, online_retail.yaml
    metrics/definitions.md, compute.py
    protocol/io_spec.md, timing.md, seeds.md
  experiments/                     ← 実験実行入口・結果索引
    gen_synthetic.py               ← 合成データ生成 + GT 計算
    run_phase1.py                  ← Phase1 vs 従来法 実行・計時
    run_stage_A.py                 ← Stage A オーケストレーター
    analyze_results.py             ← 結果集計テーブル出力
    configs/                       ← 実験条件 YAML（exp001/010/020）
    registry/experiments.csv       ← 実験台帳
    reports/tables/, reports/figures/
    results/                       ← 実験生データ（a1/a2/a3/a4_full_*）
    doc/
      experiment_design.md         ← 設計インデックス
      experiment_design_stage_a.md ← Stage A 詳細
      experiment_design_stage_b.md ← Stage B 詳細
      stage_a_runbook.md           ← Stage A 実行手順書
  runs/                            ← 実行結果生データ（.gitignore 対象）
  paper/
    manuscript/                    ← LaTeX 原稿（旧 paper_basket/）
      main.tex, refs.bib, sec/, fig/, alg/
    target/dsaa2025/               ← DSAA2025 提出物（旧 DSAA2025/）
    target/main_manuscript/OVERVIEW.md
    bibliography/OVERVIEW.md
    reproducibility_appendix/      ← 再現性資料（environment.md 等）
  tools/
    scripts/                       ← format.sh, lint.sh, gen_figs.py, freeze_env.sh
    prompts/                       ← 文章生成用プロンプト資産
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
# Rust（全テスト）
cd apriori_window_suite && cargo test

# Python（全テスト）
python3 -m pytest apriori_window_suite/python/tests/ -v

# 特定モジュールのみ
cd apriori_window_suite && cargo test interval
python3 -m pytest apriori_window_suite/python/tests/test_basket.py -v
```

### 実行

```sh
# Phase 1（デフォルト設定）
cd apriori_window_suite && cargo run -- phase1

# Phase 2（設定ファイル指定）
cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json

# Python Phase 1 / Phase 2
python3 apriori_window_suite/python/apriori_window_basket.py [settings.json]
python3 apriori_window_suite/python/event_correlator.py [settings.json]

# 比較手法バイナリビルド
cd apriori_window_suite && cargo build --release --bin comparative_mining

# 比較手法スモーク実行
python3 -m baselines.runner.run_stage_a_suite \
  --input-basket apriori_window_suite/data/sample_basket.txt \
  --out-dir baselines/results/smoke_test --backend auto --minsup-count 1 --max-length 3
```

### ビルド

```sh
cd apriori_window_suite && cargo build --release
```

### 開発補助

```sh
bash tools/scripts/format.sh   # Rust + Python フォーマット
bash tools/scripts/lint.sh     # Rust clippy + Python ruff
python3 tools/scripts/gen_figs.py  # 論文図表生成（実験結果→paper/）
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
| 時間的関係 | 6種: DFE / EFD / DCE / ECD / DOE / EOD（詳細は `apriori_window_suite/doc/OVERVIEW.md`） |
| 比較手法実行 | `baselines.runner.*` モジュール + Rust バイナリ `comparative_mining` |

---

## 5. Git / PR Workflow

- **作業ブランチ**: `dev_takayasu`（現在）、新機能は `feature/<name>` を切る
- **マージ先**: `main`
- **コミット粒度**: 1コミット1意図（Python prototype / Rust port / test add / doc update は別コミット）
- **PR に書くこと**: 変更点 / テスト結果（passed件数）/ 影響範囲

---

## 6. Skills

スキルは `.agents/skills/` で管理。`/skill-name` 形式で呼び出し可能。

**リポジトリ固有スキル**:

| Skill | 使う場面 |
|-------|---------|
| `impl-feature` | 新しいアルゴリズム機能の追加（Python prototype → Rust port） |
| `run-experiment` | 実験実行と結果記録（Phase 3） |
| `update-docs` | コード変更後のドキュメント整合性確認・更新 |
| `git-workflow` | コミット分割・PR 作成・push 前チェック |
| `debug-test` | Rust / Python テスト失敗の原因特定と修正 |
| `write-paper` | Phase 1 拡張論文の執筆・改訂 |

**マーケットプレイス スキル**:

| Skill | 使う場面 |
|-------|---------|
| `rust-best-practices` | Rust コードの品質・パターン確認 |
| `python-testing-patterns` | pytest パターン・テスト設計 |
| `git-advanced-workflows` | 高度な git 操作（rebase・cherry-pick 等） |
| `ml-paper-writing` | ML 系論文の執筆ガイド（NeurIPS/ICML/ICLR テンプレート付き） |

---

## 7. Test Baseline

変更前後でこの件数を下回ったら問題：

| 対象 | 件数 |
|------|------|
| Rust lib テスト | 54 |
| Rust main（E2E）テスト | 4 |
| Python Phase 1 pytest | 24 |
| Python Phase 2 pytest | 40 |

---

## 8. Path Migration Notes（AI 向け注意）

このリポジトリは 2026-03-04 に構造を再編した。古いパスへの参照が残っている場合は以下の対応表で修正する：

| 旧パス | 新パス |
|--------|--------|
| `comparative_methods/` | `baselines/` |
| `comparative_methods.runner` | `baselines.runner` |
| `paper_basket/` | `paper/manuscript/` |
| `DSAA2025/` | `paper/target/dsaa2025/` |
| `apriori_window_suite/doc/README.md` | `apriori_window_suite/doc/OVERVIEW.md` |
| `apriori_window_suite/doc/experiment_design.md` | `experiments/doc/experiment_design.md` |

---

## 9. AI Assistant Quick Reference

### よくある質問と回答

**Q: テストが通るか確認したい**
```sh
cd apriori_window_suite && cargo test && python3 -m pytest apriori_window_suite/python/tests/ -v
```

**Q: Phase 1 の出力 `(s, e)` は何を意味するか？**
→ 「密集条件を満たすウィンドウ左端 l の連続区間」。実際の密集期間は `[s, e+W]`。

**Q: 論文の LaTeX をコンパイルしたい**
```sh
cd paper/manuscript && latexmk -pdf -interaction=nonstopmode main.tex
```

**Q: 比較手法を実行したい**
```sh
# まずビルド
cd apriori_window_suite && cargo build --release --bin comparative_mining
# 実行（baselines.runner モジュールを使う）
python3 -m baselines.runner.run_method --config baselines/runner/configs/example_apriori.json
```

**Q: 合成データを生成したい**
```sh
python3 experiments/gen_synthetic.py
```

**Q: 実験結果はどこにあるか？**
→ `experiments/results/` 配下（a1/a2/a3/a4_full_20260302 等）。台帳は `experiments/registry/experiments.csv`。

**Q: `doc/` 参照が複数あって混乱する**
→ `apriori_window_suite/doc/` = 実装詳細。`experiments/doc/` = 実験設計。`paper/reproducibility_appendix/` = 再現性資料。

---

## 10. Correction Log（再発防止ルール）

`.claude/corrections.md` に実装修正ログを蓄積している。**タスク開始前に必ず一読すること。**

### 昇格済みルール（corrections.md から抽出）

現在昇格済みルールなし。同タグ3件に達したら随時ここに追記する。

### 運用フロー

```
ユーザーから修正指示を受ける
    ↓
.claude/corrections.md に追記（根本原因・タグ付き）
    ↓
同タグが 3 件 → CLAUDE.md §10 昇格済みルールに追加
    ↓
コード修正の場合 → テストも追加
```
