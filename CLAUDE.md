# CLAUDE.md — apriori_window

## 0. Repository Purpose

- **目的**: Apriori + スライディングウィンドウで密集アイテムセット区間を検出し、サポート変動を外部イベントに帰属させる
- **主要成果物**: `apriori_window_suite/` クレート（Rust + Python 二重実装）
- **現在のフェーズ**: Phase 1 完了 → Phase 2 再設計中（Event Attribution Pipeline）
- **Phase 2 設計**: `doc/temporal_relation_pipeline.md` — 変化点検出 + イベント帰属 + 置換検定

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
    dunnhumby/                     ← Dunnhumby データ（git 管理外）
  apriori_window_suite/            ← メイン実装クレート（Rust + Python）
    Cargo.toml
    src/                           ← Rust（lib.rs, main.rs, apriori.rs, basket.rs,
    │                                  correlator.rs, interval.rs, io.rs, util.rs）
    python/
      apriori_window_basket.py     ← Phase 1 Python 実装
      event_attribution.py         ← Phase 2 Python 実装（イベント帰属パイプライン）
      tests/test_basket.py         ← 24 件
      tests/test_event_attribution.py ← 57 件
    data/                          ← サンプルデータ・settings*.json
    doc/
      OVERVIEW.md                  ← 実装詳細・API
      impl_log.md                  ← 実装変更履歴
  experiments/                     ← 実験実行入口
    run_ex1.py                     ← EX1: コア帰属精度
    run_ex2.py                     ← EX2: アブレーション分析
    run_method_comparison.py       ← EX3: 関連手法比較（7手法）
    run_ex4_dunnhumby.py           ← EX4: Dunnhumby 実データ検証
    run_null_fdr.py                ← 帰無条件 FDR 検証
    run_baseline_comparison.py     ← ベースライン比較（査読対応）
    run_hypothesis_analysis.py     ← 仮説数分析
    run_appendix_semi_synthetic.py ← 付録: 半合成データ検証
    analyze_pvalues.py             ← p値分布分析・図表生成
    gen_fig_pipeline_example.py    ← パイプライン例示図生成
    preprocess_dunnhumby.py        ← Dunnhumby データ前処理
    src/                           ← 実験共通モジュール
      gen_synthetic.py             ← 合成データ生成 + 正解計算
      run_experiment.py            ← 実験実行共通ロジック
      evaluate.py                  ← 評価関数（P/R/F1/FAR）
      wilcoxon_baseline.py         ← Wilcoxon ベースライン
      causalimpact_baseline.py     ← CausalImpact ベースライン
      method_baselines.py          ← ITS/EventStudy/EP-Contrast/ECA ベースライン
    results/                       ← 実験結果 JSON
    doc/                           ← 実験設計ドキュメント
  paper/
    manuscript/                    ← LaTeX 原稿
      main.tex, refs.bib, sec/, fig/, alg/
    target/dsaa2025/               ← DSAA2025 提出物
    reproducibility_appendix/      ← 再現性資料
    review/                        ← 査読フィードバック
  doc/
    temporal_relation_pipeline.md  ← Phase 2 パイプライン設計
    related_work_survey.md         ← 関連研究サーベイ
  research/future_directions/      ← 論文展開戦略
  tools/scripts/                   ← format.sh, lint.sh, gen_figs.py
  runs/                            ← 実行結果生データ（.gitignore 対象）
```

---

## 2. Working Principles

- **Rust ファースト**: 機能追加は最初から Rust で直接実装してよい（Python プロトタイプを経由する必要はない）
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
| 共起定義 | 同一トランザクション内 |
| スタックケース | `window_occurrences[surplus] == l` のとき `l += 1`（`interval.rs` / `interval.py`） |
| 単体アイテム出力 | `write_patterns_csv` では len==1 はスキップ |
| import 依存 | `io.rs` は他モジュールから一方向参照のみ |
| Phase 2 設計 | Event Attribution Pipeline: 変化点検出 → イベント帰属 → 置換検定（`doc/temporal_relation_pipeline.md`） |
| Python パス | `event_attribution.py` は `sys.path.insert(0, parent)` で `apriori_window_basket` を import |

---

## 5. Git / PR Workflow

- **作業ブランチ**: `main`（安定版）、各論文は `paper/<paper-id>` を切る
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
| `run-experiment` | 実験実行と結果記録 |
| `update-docs` | コード変更後のドキュメント整合性確認・更新 |
| `git-workflow` | コミット分割・PR 作成・push 前チェック |
| `debug-test` | Rust / Python テスト失敗の原因特定と修正 |
| `write-paper` | 学術論文の執筆・改訂 |
| `literature-survey` | 体系的文献調査・ギャップ分析・BibTeX 生成 |
| `formalize-theory` | 問題定式化・定理証明・計算量解析 |
| `build-pages` | GitHub Pages LP 作成・デプロイ |
| `run-full-pipeline` | 1 論文を Phase 1〜6 まで一気通貫で実行 |

**マーケットプレイス スキル**:

| Skill | 使う場面 |
|-------|---------|
| `rust-best-practices` | Rust コードの品質・パターン確認 |
| `python-testing-patterns` | pytest パターン・テスト設計 |
| `git-advanced-workflows` | 高度な git 操作（rebase・cherry-pick 等） |
| `ml-paper-writing` | ML 系論文の執筆ガイド（NeurIPS/ICML/ICLR テンプレート付き） |
| `research-paper-writer` | IEEE/ACM 形式の論文構成・引用管理・反復執筆プロセス |
| `latex-paper-en` | LaTeX ファイルの文法・表現・論理チェック（提出前の品質確認） |
| `venue-templates` | DSAA/ICDM 等 50+ 会議の LaTeX テンプレート取得・検証 |

---

## 7. Test Baseline

変更前後でこの件数を下回ったら問題：

| 対象 | 件数 |
|------|------|
| Rust lib テスト | 24 |
| Rust main（E2E）テスト | 1 |
| Python Phase 1 pytest | 24 |
| Python Phase 2 pytest (event_attribution) | 57 |

---

## 8. AI Assistant Quick Reference

### よくある質問と回答

**Q: テストが通るか確認したい**
```sh
cd apriori_window_suite && cargo test && python3 -m pytest apriori_window_suite/python/tests/ -v
```

**Q: Phase 1 の出力 `(s, e)` は何を意味するか？**
→ 「密集条件を満たすウィンドウ左端 l の連続区間」。実際の密集期間は `[s, e+W]`。

**Q: 論文の LaTeX をコンパイルしたい**
```sh
cd paper/manuscript && latexmk -xelatex -interaction=nonstopmode main.tex
```

**Q: 実験を実行したい**
```sh
python3 experiments/run_ex1.py            # EX1: コア帰属精度
python3 experiments/run_ex2.py            # EX2: アブレーション
python3 experiments/run_method_comparison.py  # EX3: 手法比較
python3 experiments/run_ex4_dunnhumby.py   # EX4: Dunnhumby 実データ
```

**Q: 実験結果はどこにあるか？**
→ `experiments/results/` 配下（ex1/, ex2/, method_comparison/, null_fdr/ 等）。

**Q: `doc/` 参照が複数あって混乱する**
→ `apriori_window_suite/doc/` = 実装詳細。`experiments/doc/` = 実験設計。`paper/reproducibility_appendix/` = 再現性資料。

---

## 9. Correction Log（再発防止ルール）

`.claude/corrections.md` に実装修正ログを蓄積している。**タスク開始前に必ず一読すること。**

### 昇格済みルール（corrections.md から抽出）

現在昇格済みルールなし。同タグ3件に達したら随時ここに追記する。

### 運用フロー

```
ユーザーから修正指示を受ける
    ↓
.claude/corrections.md に追記（根本原因・タグ付き）
    ↓
同タグが 3 件 → CLAUDE.md §9 昇格済みルールに追加
    ↓
コード修正の場合 → テストも追加
```
