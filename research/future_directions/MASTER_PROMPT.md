# Master Prompt: 17 論文プロジェクト オーケストレーション

> **目的**: Apriori-Window を起点とする「密集区間マイニング」研究ラインの 17 本 + α の論文を、
> 研究・実装・実験・論文執筆・GitHub Pages 公開まで一貫して遂行する。

---

## -1. オーケストレーション原則（最重要・全フェーズに適用）

### 実行姿勢

1. **止まるな、走り抜け**: 各論文は Phase 1〜6 を途中で止めず最後まで完走する。ユーザーの承認待ちで止まらない。判断に迷ったら最善と思われる選択をして進め、後から修正する方が価値が高い。
2. **トークンを節約するな**: 品質を最大化せよ。文献調査は徹底的に、実装は丁寧に、実験は網羅的に、論文は完成度高く。「短く済ませる」より「正しく完成させる」を優先する。
3. **並列でガンガン回せ**: 独立したタスクは常に並列実行する。Agent ツールを複数同時起動し、待ち時間を最小化する。1 つの論文内でも Research Agent / Implementation Agent / Experiment Agent を同時に走らせられる場合は走らせる。

### エージェントチーム編成

4. **常に最適なエージェントチームを構成する**: タスクの性質に応じて以下の役割を持つエージェントを動的に編成する。1 人で全部やるな。

| 役割 | 担当内容 | 使うツール |
|------|---------|-----------|
| **Researcher** | 文献調査・ギャップ分析・理論検証 | WebSearch, WebFetch, Read, Grep |
| **Architect** | 問題定式化・アルゴリズム設計・証明 | Read, Write, Edit |
| **Coder** | Python プロトタイプ・Rust 移植・テスト | Write, Edit, Bash, Grep |
| **Experimenter** | 実験設計・実行・結果分析・図表生成 | Bash, Write, Read |
| **Writer** | 論文執筆・LaTeX 整形・参考文献管理 | Write, Edit, Read, Bash |
| **Designer** | GitHub Pages LP 作成・デザイン統一 | Write, Read |
| **Reviewer** | 品質チェック・テスト実行・整合性確認 | Bash, Read, Grep |

**編成例**:
```
論文 A の Phase 3 (Implementation):
  [並列] Coder Agent 1: Python プロトタイプ (反密集区間)
  [並列] Coder Agent 2: Python プロトタイプ (コントラスト密集)
  [後続] Reviewer Agent: テスト実行・品質チェック
  [後続] Coder Agent 3: Rust 移植
```

```
Wave 1 全体:
  [並列] 論文 A チーム: Researcher + Architect + Coder
  [並列] 論文 B チーム: Researcher + Architect + Coder
  [並列] Pages Designer: インデックスページ作成
```

### スキル管理

5. **必要なスキルは適宜作成する**: 既存スキル（`.agents/skills/`）で対応できない作業パターンが出てきたら、新しいスキルを作成して `.agents/skills/<skill-name>/SKILL.md` に配置する。スキルは再利用可能な形で設計する。

既存スキルで不足する可能性がある領域:
- `literature-survey`: 体系的文献調査（WebSearch → 構造化レビュー）
- `formalize-theory`: 問題定式化・定理証明・計算量解析
- `build-pages`: GitHub Pages LP の作成・デプロイ
- `run-full-pipeline`: 1 論文を Phase 1〜6 まで一気通貫で実行
- `cross-paper-sync`: 複数論文間の引用整合性・共通基盤の同期

### 質問・ユーザーアクション管理

6. **質問は最初にまとめて行う**: 作業開始前に不明点を洗い出し、一括で質問する。作業中に質問で止まるな。
7. **作業中の質問・ユーザーアクションは別ファイルに蓄積する**: 作業中にユーザー判断が必要な事項が出てきた場合、`paper/<paper-id>/PENDING_QUESTIONS.md` に記録して作業を続行する。最善の仮判断を記載し、ユーザーが後から確認・修正できるようにする。

`PENDING_QUESTIONS.md` のフォーマット:
```markdown
# Pending Questions — 論文 {PAPER_ID}

## Q1: [質問タイトル]
- **文脈**: どのフェーズ・どの作業中に発生したか
- **選択肢**: A) ... / B) ... / C) ...
- **仮判断**: B を選択して作業を続行
- **理由**: ...
- **影響範囲**: この判断を変更した場合に修正が必要なファイル
- **ステータス**: 🟡 仮判断で続行中 / ✅ ユーザー承認済み / 🔴 要修正

## Q2: ...
```

8. **ユーザーアクションが必要なタスク**（データセットのダウンロード、外部サービスの認証、産業連携の手配など）も同様に `PENDING_ACTIONS.md` に記録する:

```markdown
# Pending Actions — 論文 {PAPER_ID}

## A1: [アクションタイトル]
- **必要な理由**: ...
- **手順**: ...
- **ブロック対象**: このアクションなしでは Phase X の Step Y が実行不能
- **回避策**: アクション完了前でも「{代替手段}」で仮進行可能
- **ステータス**: 🟡 未着手 / 🔵 進行中 / ✅ 完了
```

### 進捗管理

9. **各論文の README.md にステータスダッシュボードを維持する**:

```markdown
# 論文 A: Anti-Dense Intervals and Contrast Dense Patterns

## Status Dashboard
| Phase | Status | Progress | Last Updated |
|-------|--------|----------|-------------|
| Research | ✅ Complete | 100% | 2026-03-25 |
| Formalization | ✅ Complete | 100% | 2026-03-28 |
| Implementation | 🔵 In Progress | 60% | 2026-04-01 |
| Experiments | ⬜ Not Started | 0% | - |
| Paper Writing | ⬜ Not Started | 0% | - |
| Pages | ⬜ Not Started | 0% | - |
```

10. **全体進捗は `research/future_directions/PROGRESS.md` で一覧管理する**:

```markdown
# 17 Papers Progress Tracker

| Paper | Branch | Phase | % | Venue | Deadline |
|-------|--------|-------|---|-------|----------|
| A | paper/A-anti-dense-contrast | Implementation | 60% | DSAA 2026 | TBD |
| B | paper/B-rare-dense | Research | 30% | KDD 2026 | TBD |
| ... |
```

---

## 0. 全体方針

### 0.1 ブランチ戦略

```
main (安定版・全論文の共通基盤)
 ├── paper/A-anti-dense-contrast       ← 論文 A
 ├── paper/B-rare-dense                ← 論文 B
 ├── paper/C-multidimensional          ← 論文 C
 ├── paper/D-causal-attribution        ← 論文 D
 ├── paper/E-topk-adaptive-window      ← 論文 E
 ├── paper/F-mdl-summary               ← 論文 F
 ├── paper/G-sequential-dense          ← 論文 G
 ├── paper/H-dense-prediction          ← 論文 H
 ├── paper/I-high-utility              ← 論文 I
 ├── paper/J-differential-privacy      ← 論文 J
 ├── paper/K-pharmacoepidemiology      ← 論文 K
 ├── paper/L-manufacturing             ← 論文 L
 ├── paper/M-cybersecurity             ← 論文 M
 ├── paper/N-genomics                  ← 論文 N
 ├── paper/O-attention-features        ← 論文 O
 ├── paper/P-llm-interpretation        ← 論文 P
 └── paper/Q-foundation-model          ← 論文 Q
```

- 各ブランチは `main` から切る
- 共通基盤の改善は `main` に直接コミットし、各ブランチは定期的に `main` を rebase/merge する
- 論文完成後は `main` にマージし、ブランチを削除する

### 0.2 ディレクトリ構造（各論文共通）

```
paper/<paper-id>/
├── README.md                    ← 論文概要・ステータス・リンク集
├── research/
│   ├── literature_review.md     ← 関連研究サーベイ
│   ├── gap_analysis.md          ← 既存研究とのギャップ分析
│   └── formalization.md         ← 問題定式化・定理・証明
├── implementation/
│   ├── design.md                ← 実装設計書
│   ├── python/                  ← Python プロトタイプ
│   │   ├── <module>.py
│   │   └── tests/test_<module>.py
│   └── rust/                    ← Rust 移植（apriori_window_suite/src/ への差分）
├── experiments/
│   ├── design.md                ← 実験設計書
│   ├── configs/                 ← 実験設定 YAML/JSON
│   ├── runners/                 ← 実験実行スクリプト
│   ├── results/                 ← 実験結果データ
│   └── analysis.md              ← 結果分析・考察
├── manuscript/
│   ├── main.tex                 ← LaTeX 原稿
│   ├── refs.bib                 ← 参考文献
│   ├── sec/                     ← セクション別 .tex
│   ├── fig/                     ← 図表
│   └── alg/                     ← アルゴリズム擬似コード
└── pages/
    └── index.html               ← GitHub Pages 用 LP（ランディングページ）
```

### 0.3 ワークフロー（全論文共通・6 フェーズ）

```
Phase 1: Research        (2-3 週間)
Phase 2: Formalization   (1-2 週間)
Phase 3: Implementation  (2-4 週間)
Phase 4: Experiments     (2-3 週間)
Phase 5: Paper Writing   (3-4 週間)
Phase 6: Pages & Polish  (1 週間)
```

---

## 1. フェーズ別プロンプトテンプレート

### Phase 1: Research（文献調査・ギャップ分析）

```
あなたは密集区間マイニングの研究者です。
論文「{PAPER_TITLE}」の文献調査を行います。

## タスク
1. 以下の研究領域の関連論文を 20-30 本調査してください:
   - {RESEARCH_AREA_1}
   - {RESEARCH_AREA_2}
   - {RESEARCH_AREA_3}

2. 各論文について以下を記録してください:
   - 著者・年・会議/ジャーナル
   - 手法の概要（3行）
   - 本研究との関連性
   - 本研究の差別化ポイント

3. ギャップ分析を作成してください:
   - 既存手法の限界を表形式で整理
   - 本研究が埋めるギャップを明確化
   - 「なぜ今まで誰もやらなかったのか」への回答

## 出力先
- `paper/{PAPER_ID}/research/literature_review.md`
- `paper/{PAPER_ID}/research/gap_analysis.md`

## 参照
- `research/future_directions/{SOURCE_FILE}` の該当セクション
- 現行論文: `paper/manuscript/sec/02_related_work.tex`

## 品質基準
- 2024-2026 の最新論文が 5 本以上含まれていること
- BibTeX エントリが `paper/{PAPER_ID}/manuscript/refs.bib` に追加されていること
- ギャップが定量的に（「X は Y をしない」形式で）記述されていること
```

### Phase 2: Formalization（問題定式化）

```
あなたは理論計算機科学の研究者です。
論文「{PAPER_TITLE}」の問題定式化を行います。

## タスク
1. 以下の概念を数学的に定義してください:
   {CONCEPTS_TO_DEFINE}

2. 以下の定理を証明してください（証明が自明でない場合は証明スケッチ）:
   {THEOREMS_TO_PROVE}

3. 計算量を解析してください:
   - ナイーブアルゴリズムの時間計算量
   - 提案アルゴリズムの時間計算量
   - 空間計算量

## 出力先
- `paper/{PAPER_ID}/research/formalization.md`
- `paper/{PAPER_ID}/manuscript/sec/03_problem_definition.tex`

## 制約
- 定義は Apriori-Window 原論文の表記を踏襲すること
  - トランザクション DB: D, パターン: P, サポート: s_P(l), 窓幅: W, 閾値: θ
- 新概念は既存概念の自然な拡張として定義すること
- LaTeX の定義環境を使用: \begin{definition}...\end{definition}

## 参照
- 現行論文の定義: `paper/manuscript/sec/03_problem_definition.tex`
- Apriori-Window 原論文: `paper/target/dsaa2025/`
```

### Phase 3: Implementation（Python プロトタイプ → Rust 移植）

```
あなたは apriori_window_suite の開発者です。
論文「{PAPER_TITLE}」のアルゴリズムを実装します。

## 作業原則
1. Python → Rust の二段構成を厳守
2. テストを壊さない（既存テスト全 passed を維持）
3. 最小差分の原則

## タスク

### Step 1: 設計書作成
- `paper/{PAPER_ID}/implementation/design.md` に以下を記述:
  - 変更対象モジュール一覧
  - 新規関数/構造体の API 設計
  - 既存コードへの影響範囲

### Step 2: Python プロトタイプ
- 実装先: `paper/{PAPER_ID}/implementation/python/`
- 新モジュール: `{MODULE_NAME}.py`
- テスト: `paper/{PAPER_ID}/implementation/python/tests/test_{MODULE_NAME}.py`
  - 正常系 5 件以上
  - 境界値 3 件以上
  - 異常系 2 件以上
- テスト実行:
  ```sh
  python3 -m pytest paper/{PAPER_ID}/implementation/python/tests/ -v
  ```

### Step 3: Rust 移植
- 実装先: `apriori_window_suite/src/` の適切なファイル（新規 or 既存）
- `lib.rs` の `pub use` を更新
- テスト: 同ファイルの `mod tests` に追記
- テスト実行:
  ```sh
  cd apriori_window_suite && cargo test
  ```

### Step 4: 統合確認
- Python と Rust で同一入力に対して同一出力を確認
- `apriori_window_suite/doc/impl_log.md` に変更内容を追記

## 品質基準
- 既存テスト件数を下回っていないこと
- スタックケース保護が維持されていること
- `cargo clippy` で warning が出ないこと

## 参照
- 既存実装: `apriori_window_suite/src/interval.rs`, `apriori.rs`, `basket.rs`
- Python 実装: `apriori_window_suite/python/apriori_window_basket.py`
- Phase 2 実装: `apriori_window_suite/python/event_attribution.py`
```

### Phase 4: Experiments（実験設計・実行・分析）

```
あなたは実験科学者です。
論文「{PAPER_TITLE}」の実験を設計・実行・分析します。

## 実験設計の原則
1. 合成データで制御された検証 → 実データで実用性を実証
2. アブレーション研究で各要素の貢献を定量化
3. 再現可能性: 全パラメータを設定ファイルに記録

## タスク

### Step 1: 実験設計書
`paper/{PAPER_ID}/experiments/design.md` に以下を記述:
- 研究質問 (RQ) を 3-5 個定義
- 各 RQ に対応する実験 (E1-E5) を定義
- データセット・パラメータ・評価指標を明示

### Step 2: 合成データ実験
{SYNTHETIC_EXPERIMENTS}

### Step 3: 実データ実験
{REAL_DATA_EXPERIMENTS}

### Step 4: アブレーション / パラメータ感度分析
{ABLATION_EXPERIMENTS}

### Step 5: 結果分析
- `paper/{PAPER_ID}/experiments/analysis.md` に結果と考察を記述
- 図表を `paper/{PAPER_ID}/manuscript/fig/` に生成
- LaTeX テーブルを `paper/{PAPER_ID}/manuscript/sec/05_experiments.tex` に記述

## 品質基準
- 各実験が 5 seed 以上で実行されていること（平均 ± 標準偏差を報告）
- 既存手法との比較が含まれていること
- 実行時間が報告されていること
- 全設定ファイルが `paper/{PAPER_ID}/experiments/configs/` に保存されていること

## 参照
- 既存実験パターン: `experiments/doc/experiment_design.md`
- 合成データ生成: `experiments/gen_synthetic.py`
- 結果分析パターン: `experiments/doc/experiment_report.md`
```

### Phase 5: Paper Writing（論文執筆）

```
あなたは学術論文の著者です。
論文「{PAPER_TITLE}」を執筆します。

## 論文構成
```
1. Introduction
2. Related Work
3. Problem Definition / Preliminaries
4. Proposed Method
5. Experiments
6. Conclusion
```

## 各セクションの要件

### Introduction (1-1.5 ページ)
- 段落 1: 問題の動機（なぜ重要か）
- 段落 2: 既存手法の限界（gap_analysis.md から）
- 段落 3: 本研究の提案と貢献リスト
- 段落 4: 論文の構成

### Related Work (1-1.5 ページ)
- literature_review.md の内容を学術的文体に変換
- 本研究との差異を各段落の末尾に明記

### Problem Definition (1 ページ)
- formalization.md の定義・定理を LaTeX 化
- 各定義の直後に具体例

### Proposed Method (2-3 ページ)
- アルゴリズム疑似コード（Algorithm 環境）
- 計算量の証明
- 正当性の証明（定理として）

### Experiments (2-3 ページ)
- analysis.md の結果を表・図で提示
- 各 RQ に対する回答を明確に

### Conclusion (0.5 ページ)
- 貢献の要約
- 制約事項
- 将来課題（他の論文への布石）

## 執筆ルール
- 英語で執筆（投稿先が英語会議/ジャーナルの場合）
- 能動態優先（"We propose..." not "It is proposed..."）
- 定量的主張には必ず数値を添える
- Apriori-Window 原論文を必ず引用
- 用語統一: `paper/manuscript/` の既存論文の表記に合わせる

## 出力先
- `paper/{PAPER_ID}/manuscript/`

## 参照
- 既存論文テンプレート: `paper/manuscript/main.tex`
- BibTeX: `paper/{PAPER_ID}/manuscript/refs.bib`
- LaTeX スキル: `/latex-paper-en`
```

### Phase 6: GitHub Pages（LP 作成・公開）

```
あなたは研究プロジェクトの Web デザイナーです。
論文「{PAPER_TITLE}」の GitHub Pages ランディングページを作成します。

## タスク

### Step 1: 論文 LP 作成
`paper/{PAPER_ID}/pages/index.html` に以下を含む単一 HTML を作成:

- **ヘッダー**: 論文タイトル・著者・投稿先バッジ
- **概要セクション**: Abstract の日本語版
- **手法セクション**: アルゴリズムの視覚的説明（図・フローチャート）
- **実験結果セクション**: 主要な表・グラフ（SVG or Canvas）
- **コードセクション**: インストール・実行方法
- **論文リンク**: PDF ダウンロード（準備中の場合は Coming Soon）

### Step 2: スタイル要件
- 既存 LP (`gh-pages` ブランチの `index.html`) と統一したデザイン
- レスポンシブ対応（モバイル表示可能）
- CSS/JS はインライン（外部依存なし）
- 日本語 UI

### Step 3: インデックスページ更新
`index.html`（ルート）を更新し、全論文への導線を追加:
- カード形式で各論文を表示
- ステータスバッジ（研究中 / 実装中 / 実験中 / 執筆中 / 投稿済み）
- Tier 別のグルーピング

## デプロイ
- `gh-pages` ブランチに配置
- ディレクトリ構造:
  ```
  gh-pages/
  ├── index.html                    ← 全体インデックス
  ├── paper/A/index.html            ← 論文 A の LP
  ├── paper/B/index.html            ← 論文 B の LP
  └── ...
  ```
```

---

## 2. 論文定義一覧

### Tier 1: 高新規性 × 高実現可能性（短期）

#### 論文 A: 反密集区間 + コントラスト密集パターン
```yaml
paper_id: A-anti-dense-contrast
branch: paper/A-anti-dense-contrast
title: "Anti-Dense Intervals and Contrast Dense Patterns: Symmetric Extensions of Dense Interval Mining"
title_ja: "反密集区間とコントラスト密集パターン: 密集区間マイニングの対称的拡張"
venue: DSAA 2026 / ICDM 2026
difficulty: 2/5
novelty: Very High

research_areas:
  - 稀パターンマイニング (RP-Growth, 否定的相関ルール)
  - エマージングパターン (Dong & Li 1999)
  - 時系列変化検出 (CUSUM, PELT)
  - 概念ドリフト検出

concepts_to_define:
  - Anti-Dense Interval (反密集区間)
  - Contrast Dense Pattern (コントラスト密集パターン)
  - Pattern Topology Change (パターン位相変化)
  - Dense Interval Structure Comparison (密集区間構造比較)

core_implementation:
  - interval.rs の閾値交差方向反転で反密集区間を検出
  - 2 レジーム間の密集区間構造比較（消失/出現/増幅/縮退の分類）
  - 構造変化の統計的検定（置換検定の拡張）

experiments:
  - E1: 合成データで反密集区間の Ground Truth 回復
  - E2: 合成データでコントラストパターンの分類精度
  - E3: パラメータ感度分析 (θ_low, レジーム分割点)
  - E4: 実データ (Dunnhumby) でのキャンペーン終了後のパターン消失検出
  - E5: 実データ (Online Retail) での季節変動コントラスト

dependencies: []
cites: [Apriori-Window原論文, Event Attribution論文]
cited_by: [K, L]
```

#### 論文 B: 稀密集パターン
```yaml
paper_id: B-rare-dense
branch: paper/B-rare-dense
title: "Rare Dense Patterns: Mining Locally Dense but Globally Rare Itemsets"
title_ja: "稀密集パターン: 局所的に密集だがグローバルに稀なアイテムセットのマイニング"
venue: KDD 2026 / SDM 2026
difficulty: 3/5
novelty: Very High

research_areas:
  - 稀パターンマイニング (RP-Growth, ARIMA)
  - 異常検出 (Isolation Forest, LOF)
  - 局所サポートと大域サポートの乖離
  - バースト検出 (Kleinberg 2002)

concepts_to_define:
  - Rare Dense Pattern (稀密集パターン)
  - Global Rarity Condition (大域稀少条件)
  - Local Density Condition (局所密集条件)
  - Two-Phase Mining (2段階マイニング)

core_implementation:
  - Apriori 枝刈りの再設計 (局所密集条件による候補回復)
  - 反単調性の再定義と証明
  - 2段階マイニングアルゴリズム

experiments:
  - E1: 合成データで稀密集パターンの回復率 (vs Apriori-Window, vs RP-Growth)
  - E2: 枝刈り効率の比較 (候補数・実行時間)
  - E3: スケーラビリティ (N=1K-1M)
  - E4: 実データでの稀密集パターン発見事例

dependencies: []
cites: [Apriori-Window原論文]
cited_by: [M]
```

### Tier 2: 高新規性 × 中難度（中期）

#### 論文 C: 多次元密集領域マイニング
```yaml
paper_id: C-multidimensional
branch: paper/C-multidimensional
title: "Multi-Dimensional Dense Region Mining: From Intervals to Level Sets of Support Surfaces"
title_ja: "多次元密集領域マイニング: サポート曲面のレベルセットとしての密集領域"
venue: KDD 2027 / ICDM 2026
difficulty: 4/5
novelty: Very High

research_areas:
  - 空間データマイニング (SaTScan, DBSCAN)
  - テンソル分解 (DenseAlert, M-Zoom)
  - 空間的共局在マイニング
  - スウィープライン法

concepts_to_define:
  - Support Surface (サポート曲面)
  - Dense Region (密集領域)
  - Dense Region Containment Theorem (密集領域包含定理)
  - Dimension Decomposability (次元分解可能性)

core_implementation:
  - 2D プロトタイプ (時間×空間) in Python
  - スウィープ面法アルゴリズム
  - グリッド離散化による高速化
  - Rust 移植

experiments:
  - E1: 合成データ (植え込み密集領域の回復)
  - E2: 次元分解の精度と速度のトレードオフ
  - E3: スケーラビリティ (2D, 3D)
  - E4: 実データ (店舗位置付き Dunnhumby or 疫学データ)

dependencies: []
cites: [Apriori-Window原論文]
cited_by: [N, TKDE拡張]
```

#### 論文 D: 因果帰属への昇格
```yaml
paper_id: D-causal-attribution
branch: paper/D-causal-attribution
title: "From Association to Causation: Synthetic Control for Dense Pattern Attribution"
title_ja: "関連から因果へ: 密集パターン帰属のための合成コントロール法"
venue: KDD 2027 / AAAI 2027
difficulty: 4/5
novelty: Very High

research_areas:
  - 合成コントロール法 (Abadie+ 2010)
  - 差分の差分法 (Difference-in-Differences)
  - 因果推論 (Rubin Causal Model)
  - 介入時系列分析 (CausalImpact)

concepts_to_define:
  - Donor Pool (ドナープール)
  - Counterfactual Support Trajectory (反事実サポート軌道)
  - Causal Effect on Support (サポートへの因果効果)
  - Item-Disjoint Pattern Control (アイテム非共有パターンコントロール)

core_implementation:
  - 合成コントロール法のパターンサポート時系列への適用
  - ドナープール構築 (アイテム非共有パターンの選択)
  - 反事実推定と因果効果の信頼区間
  - Phase 2 パイプラインとの統合

experiments:
  - E1: 合成データで既知因果効果の回復精度
  - E2: ドナープールサイズの影響
  - E3: 偽陽性率の検証 (null イベントに対する棄却率)
  - E4: 実データ (Dunnhumby キャンペーン)
  - E5: Phase 2 (置換検定) との比較

dependencies: [Event Attribution (Phase 2)]
cites: [Apriori-Window原論文, Event Attribution論文]
cited_by: [L, JMLR拡張]
```

#### 論文 E: Top-k + 適応的窓幅
```yaml
paper_id: E-topk-adaptive-window
branch: paper/E-topk-adaptive-window
title: "Parameter-Free Dense Interval Mining: Top-k Patterns with Adaptive Window Sizes"
title_ja: "パラメータフリー密集区間マイニング: 適応的窓幅による Top-k パターン"
venue: VLDB 2027 / ICDM 2027
difficulty: 4/5
novelty: High

research_areas:
  - Top-k 頻出パターンマイニング (TKS, TKO)
  - 多スケール解析 (ウェーブレット, スケール空間)
  - 分枝限定法
  - パラメータフリーマイニング

concepts_to_define:
  - Dense Coverage Score (密集カバレッジスコア)
  - Scale-Space Dense Ridge (スケール空間密集リッジ)
  - Dyadic Scale Hierarchy (ダイアディックスケール階層)
  - Branch-and-Bound Dense Pruning (分枝限定密集枝刈り)

core_implementation:
  - 多スケール密集区間計算 (W₀, 2W₀, 4W₀, ...)
  - ランキング基準の実装 (カバレッジ/最大スパン/区間数)
  - 分枝限定による効率的な Top-k 列挙
  - スケール空間リッジ検出

experiments:
  - E1: θ/W を変えた場合との品質比較
  - E2: 分枝限定の枝刈り効率
  - E3: スケーラビリティ
  - E4: 実データでのパラメータ感度解消の検証

dependencies: []
cites: [Apriori-Window原論文]
cited_by: [F, Q, VLDBJ拡張]
```

### Tier 3: 長期（高難度・高天井）

#### 論文 F: MDL 密集区間要約
```yaml
paper_id: F-mdl-summary
branch: paper/F-mdl-summary
title: "Summarizing Dense Intervals with the Minimum Description Length Principle"
title_ja: "最小記述長原理による密集区間要約"
venue: KDD / ECML-PKDD
difficulty: 4/5
novelty: High

research_areas:
  - MDL (Minimum Description Length)
  - KRIMP / SLIM / StreamKrimp
  - パターンセット選択
  - 情報理論的マイニング

concepts_to_define:
  - Temporal Code Table (時間的コードテーブル)
  - Time-Scoped Code Length (時間スコープ付き符号長)
  - Dense Interval Compression (密集区間圧縮)

dependencies: [E-topk-adaptive-window]
cites: [Apriori-Window原論文, 論文E]
```

#### 論文 G: 系列密集パターン
```yaml
paper_id: G-sequential-dense
branch: paper/G-sequential-dense
title: "Sequential Dense Patterns: Mining Temporally Ordered Co-occurrence Bursts"
title_ja: "系列密集パターン: 時間順序付き共起バーストのマイニング"
venue: KDD / VLDB
difficulty: 4/5
novelty: High

research_areas:
  - 系列パターンマイニング (PrefixSpan, SPADE)
  - エピソードマイニング
  - 時間的パターンの頻出性

concepts_to_define:
  - Sequential Dense Pattern (系列密集パターン)
  - In-Window Sequential Support (窓内系列サポート)
  - Sequential Anti-Monotonicity (系列反単調性)

dependencies: []
cites: [Apriori-Window原論文]
```

#### 論文 H: 密集区間予測
```yaml
paper_id: H-dense-prediction
branch: paper/H-dense-prediction
title: "Predicting Dense Intervals: From Descriptive to Predictive Pattern Mining"
title_ja: "密集区間予測: 記述的から予測的パターンマイニングへ"
venue: KDD / SDM
difficulty: 3/5
novelty: High

research_areas:
  - 点過程 (Hawkes Process)
  - 生存分析
  - 時系列予測 (Prophet, N-BEATS)
  - バースト予測

concepts_to_define:
  - Dense Interval Occurrence Process (密集区間発生過程)
  - Inter-Dense Interval Time (密集区間間時間)
  - Dense Duration Prediction (密集持続時間予測)

dependencies: []
cites: [Apriori-Window原論文]
```

#### 論文 I: 高ユーティリティ密集区間
```yaml
paper_id: I-high-utility
branch: paper/I-high-utility
title: "High-Utility Dense Intervals: Joint Frequency-Utility Temporal Mining"
title_ja: "高ユーティリティ密集区間: 頻度×効用の二重条件時間的マイニング"
venue: TKDE / KAIS
difficulty: 3/5
novelty: High

research_areas:
  - 高ユーティリティアイテムセットマイニング (HUI-Miner, EFIM)
  - LHUIM (Local High-Utility)
  - ユーティリティの反単調性

concepts_to_define:
  - Utility-Dense Interval (ユーティリティ密集区間)
  - Window Utility (窓内ユーティリティ)
  - Transaction Weighted Utility in Window (窓内TWU)

dependencies: []
cites: [Apriori-Window原論文]
```

#### 論文 J: 差分プライバシー密集区間
```yaml
paper_id: J-differential-privacy
branch: paper/J-differential-privacy
title: "Differentially Private Dense Interval Mining"
title_ja: "差分プライバシー密集区間マイニング"
venue: CCS / VLDB
difficulty: 5/5
novelty: High

research_areas:
  - 差分プライバシー (Dwork 2006)
  - DP頻出パターンマイニング
  - Laplace/Exponentialメカニズム
  - 感度解析

concepts_to_define:
  - Window Sensitivity (窓感度)
  - DP Dense Interval (DP密集区間)
  - Threshold Stability (閾値安定性)
  - Privacy Budget Composition (プライバシ予算合成)

dependencies: []
cites: [Apriori-Window原論文]
```

### Tier 3: 応用ドメイン（並行開発可能）

#### 論文 K: 薬剤疫学
```yaml
paper_id: K-pharmacoepidemiology
branch: paper/K-pharmacoepidemiology
title: "Dense Prescription Patterns and Regulatory Event Attribution in Pharmacoepidemiology"
title_ja: "薬剤疫学における処方パターン密集区間と規制イベント帰属"
venue: JAMIA / AMIA
difficulty: 3/5

data: MIMIC-IV
adapter: ATC コード → アイテム, 受診記録 → トランザクション

dependencies: [A-anti-dense-contrast or B-rare-dense]
cites: [Apriori-Window原論文, 論文A or B]
```

#### 論文 L: 製造業故障診断
```yaml
paper_id: L-manufacturing
branch: paper/L-manufacturing
title: "Dense Alarm Pattern Mining for Manufacturing Fault Diagnosis with Maintenance Event Attribution"
title_ja: "製造業故障診断のための密集アラームパターンマイニングと保全イベント帰属"
venue: IEEE Trans. Semiconductor Manufacturing
difficulty: 3/5

data: SECOM (UCI) + 産業連携
adapter: アラームタイプ → アイテム, 時間ビン → トランザクション

dependencies: [D-causal-attribution]
cites: [Apriori-Window原論文, 論文D]
```

#### 論文 M: サイバーセキュリティ
```yaml
paper_id: M-cybersecurity
branch: paper/M-cybersecurity
title: "Dense ATT&CK Technique Co-occurrence Mining for Cyber Threat Attribution"
title_ja: "サイバー脅威帰属のための密集 ATT&CK 技術共起マイニング"
venue: RAID / ACSAC
difficulty: 3/5

data: CICIDS 2017/2018
adapter: ATT&CK 技術ID → アイテム, 時間ビン別ネットワークセグメント → トランザクション

dependencies: [B-rare-dense]
cites: [Apriori-Window原論文, 論文B]
```

#### 論文 N: 臨床ゲノミクス
```yaml
paper_id: N-genomics
branch: paper/N-genomics
title: "Dense Gene Co-expression Intervals along Pseudotime in Single-Cell Transcriptomics"
title_ja: "シングルセルトランスクリプトミクスにおける擬時間上の密集遺伝子共発現区間"
venue: Bioinformatics / ISMB
difficulty: 3/5

data: 公開 scRNA-seq (GEO, Human Cell Atlas)
adapter: 発現閾値超遺伝子 → アイテム, 個々の細胞 (擬時間順) → トランザクション

dependencies: [C-multidimensional]
cites: [Apriori-Window原論文, 論文C]
```

### Tier 4: ML/AI 統合

#### 論文 O: Attention 帰属 + 密集パターン特徴量化
```yaml
paper_id: O-attention-features
branch: paper/O-attention-features
title: "Learning Event Attribution with Cross-Attention and Dense Pattern Featurization"
title_ja: "Cross-Attention によるイベント帰属学習と密集パターン特徴量化"
venue: KDD / CIKM
difficulty: 3/5
novelty: High

research_areas:
  - Transformer / Cross-Attention
  - 時系列特徴量エンジニアリング
  - 説明可能 AI

dependencies: [Event Attribution (Phase 2)]
cites: [Apriori-Window原論文, Event Attribution論文]
```

#### 論文 P: LLM パターン解釈
```yaml
paper_id: P-llm-interpretation
branch: paper/P-llm-interpretation
title: "LLM-Powered Interpretation of Dense Itemset Patterns"
title_ja: "LLM による密集アイテムセットパターンの自然言語解釈"
venue: KDD Demo / AAAI Demo
difficulty: 2/5
novelty: Medium-High

dependencies: [Event Attribution (Phase 2)]
cites: [Apriori-Window原論文, Event Attribution論文]
```

#### 論文 Q: トランザクション基盤モデル
```yaml
paper_id: Q-foundation-model
branch: paper/Q-foundation-model
title: "Transaction Foundation Models for Dense Interval Detection"
title_ja: "密集区間検出のためのトランザクション基盤モデル"
venue: NeurIPS / KDD
difficulty: 4/5
novelty: High

dependencies: [E-topk-adaptive-window]
cites: [Apriori-Window原論文, 論文E]
```

---

## 3. GitHub Pages 構成

### 3.1 インデックスページ (`index.html`)

全論文の一覧をカード形式で表示:
- Tier 別グルーピング
- 各カードにステータスバッジ
- クリックで各論文 LP に遷移

ステータスバッジ:
- 🔬 Research（文献調査中）
- 📐 Formalization（定式化中）
- 💻 Implementation（実装中）
- 🧪 Experiments（実験中）
- ✍️ Writing（執筆中）
- 📄 Submitted（投稿済み）
- ✅ Accepted（採択）

### 3.2 各論文 LP (`paper/<ID>/index.html`)

統一テンプレートで以下を表示:
- 論文タイトル・著者・投稿先
- Abstract
- 主要な図表・結果
- コード・データへのリンク
- 引用情報

---

## 4. 実行順序（推奨ロードマップ）

### Wave 1: 即時着手（〜3ヶ月）
```
[並列] 論文 A (反密集+コントラスト) — 難度 2/5, 最小改修
[並列] 論文 B (稀密集)              — 難度 3/5, 高新規性
```

### Wave 2: 中期（3〜6ヶ月）
```
[並列] 論文 C (多次元)              — 難度 4/5, 理論的深さ
[並列] 論文 E (Top-k+適応窓)        — 難度 4/5, パラメータフリー
[並列] 論文 K (薬剤疫学)            — 応用, A/B 完成後
```

### Wave 3: 長期（6〜12ヶ月）
```
[並列] 論文 D (因果帰属)            — 難度 4/5, 方法論的飛躍
[並列] 論文 I (高ユーティリティ)    — 難度 3/5, 実用的
[並列] 論文 O (Attention+特徴量)    — 難度 3/5, ML 統合
```

### Wave 4: 長期（12〜24ヶ月）
```
[並列] 論文 F (MDL要約)
[並列] 論文 G (系列密集)
[並列] 論文 H (密集予測)
[並列] 論文 M (セキュリティ)
[並列] 論文 N (ゲノミクス)
```

### Wave 5: 最長期（18〜36ヶ月）
```
[並列] 論文 J (差分プライバシー)
[並列] 論文 L (製造業)
[並列] 論文 P (LLM 解釈)
[並列] 論文 Q (基盤モデル)
```

---

## 5. 論文着手プロンプト（コピペ用）

### 5.1 単一論文の着手

以下を Claude Code に貼り付けて各論文の作業を開始する:

```
論文 {PAPER_ID} の作業を Phase 1〜6 まで一気通貫で実行してください。
途中で止まらず、最後まで走り抜けてください。

## 実行指示

1. `main` から `paper/{BRANCH_NAME}` ブランチを切る
2. `paper/{PAPER_ID}/` ディレクトリ構造を作成
3. `research/future_directions/MASTER_PROMPT.md` のセクション -1（オーケストレーション原則）を厳守
4. Phase 1〜6 を順に実行。各フェーズ内では並列エージェントを最大活用
5. 各フェーズ完了時にコミット（1コミット1意図）
6. 質問・ユーザーアクションは `PENDING_QUESTIONS.md` / `PENDING_ACTIONS.md` に記録して続行
7. GitHub Pages の LP を作成
8. 全体進捗を `research/future_directions/PROGRESS.md` に反映
9. 完了後、`main` にマージ

## エージェントチーム編成

Phase ごとに以下のチームを編成し、並列実行する:

### Phase 1-2 (Research + Formalization)
- [並列] Researcher Agent: 文献調査 (WebSearch → literature_review.md)
- [並列] Researcher Agent: ギャップ分析 (gap_analysis.md)
- [後続] Architect Agent: 問題定式化・定理証明 (formalization.md)
- [後続] Writer Agent: LaTeX 化 (sec/03_problem_definition.tex)

### Phase 3 (Implementation)
- [並列] Coder Agent: Python プロトタイプ
- [並列] Coder Agent: テスト作成
- [後続] Reviewer Agent: テスト実行・品質チェック
- [後続] Coder Agent: Rust 移植
- [後続] Reviewer Agent: Rust テスト実行・Python/Rust 一致確認

### Phase 4 (Experiments)
- [並列] Experimenter Agent: 合成データ実験
- [並列] Experimenter Agent: 実データ実験
- [並列] Experimenter Agent: アブレーション・スケーラビリティ
- [後続] Experimenter Agent: 結果分析・図表生成

### Phase 5 (Paper Writing)
- [並列] Writer Agent: Introduction + Related Work
- [並列] Writer Agent: Problem Definition + Proposed Method
- [並列] Writer Agent: Experiments + Conclusion
- [後続] Reviewer Agent: 全体統合・整合性チェック

### Phase 6 (Pages)
- Designer Agent: LP 作成・インデックス更新

## 必要なスキルの自動作成
既存スキルで対応できない作業パターンが出てきた場合は、
`.agents/skills/<skill-name>/SKILL.md` に新スキルを作成して使用すること。

## 参照
- 論文仕様: research/future_directions/MASTER_PROMPT.md の「論文 {PAPER_ID}」セクション
- 詳細設計: research/future_directions/{SOURCE_FILE}
- 既存実装: apriori_window_suite/
- 既存論文: paper/manuscript/
- オーケストレーション原則: MASTER_PROMPT.md セクション -1
```

### 5.2 Wave 一括着手（複数論文並列）

```
Wave {N} の論文を全て並列で着手してください。

対象論文: {PAPER_IDS}

## 実行指示

1. 対象論文ごとにブランチを切り、それぞれ独立した worktree エージェントで並列実行
2. `research/future_directions/MASTER_PROMPT.md` のセクション -1 を厳守
3. 各論文は Phase 1〜6 を完走する。途中で止めない
4. 論文間の依存関係がある場合は、先行論文の該当フェーズ完了を待って後続を開始
5. 全論文のユーザーアクション・質問は `research/future_directions/WAVE{N}_PENDING.md` に集約
6. 全論文完了後、それぞれ main にマージ

## エージェント編成

各論文に独立したエージェントチームを割り当て:

{PAPER_ID_1}: [Researcher + Architect + Coder + Experimenter + Writer + Designer]
{PAPER_ID_2}: [Researcher + Architect + Coder + Experimenter + Writer + Designer]
...

共有リソース管理:
- main ブランチへのマージは 1 論文ずつ（コンフリクト回避）
- GitHub Pages インデックスの更新は最後にまとめて実施
- 共通基盤コード（apriori_window_suite/）への変更は main に先にマージ

## トークン節約不要
品質最優先。文献調査は徹底的に、実装は丁寧に、実験は網羅的に、論文は完成度高く。
「短く済ませる」より「正しく完成させる」を優先する。
```

### 5.3 中断復帰プロンプト

```
論文 {PAPER_ID} の作業を再開してください。

1. `paper/{PAPER_ID}/README.md` のステータスダッシュボードを確認
2. `paper/{PAPER_ID}/PENDING_QUESTIONS.md` を確認し、未解決の質問があれば対応
3. 中断した Phase から再開し、最後まで完走
4. MASTER_PROMPT.md セクション -1 のオーケストレーション原則を厳守
```

---

## 6. 品質ゲート（全論文共通）

### Phase 完了判定

| Phase | 完了条件 |
|-------|---------|
| Research | literature_review.md に 20+ 論文、gap_analysis.md に明確なギャップ記述 |
| Formalization | 全定義が LaTeX 化済み、主定理に証明あり |
| Implementation | Python テスト全 passed、Rust テスト全 passed、既存テスト未破壊 |
| Experiments | 5+ seed × 3+ 実験、既存手法との比較あり、実行時間報告あり |
| Paper Writing | 全セクション完成、8+ ページ、参考文献 20+、Abstract 150-250 語 |
| Pages | LP が正常表示、インデックスページから遷移可能 |

---

*作成日: 2026-03-22*
*最終更新: 2026-03-22*
