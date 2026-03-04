---
name: write-paper
description: バスケット構造対応 Apriori-window（Phase 1）に関する学術論文の執筆・改訂。新セクションの草稿作成 / 既存セクションの改訂 / 実験結果の文章化 / 投稿テンプレへの適合に使う。
---

# Skill: write-paper

## 0. Purpose

- **このSkillが解くタスク**: バスケット構造対応 Apriori-window（Phase 1）に関する学術論文の執筆・改訂
- **使う場面**: 新セクションの草稿作成 / 既存セクションの改訂 / 実験結果の文章化 / 投稿テンプレへの適合
- **前提知識**: `paper/target/dsaa2025/` の既存論文（Apriori-window + Plant Model）が先行研究として存在する
- **できないこと（スコープ外）**: 実験の実行・データ解析・コード実装（それぞれ `run-experiment` / `impl-feature` スキルを使う）

---

## 1. 研究の位置づけ

### 1.1 先行論文（DSAA2025）の主貢献
- **Apriori-window**: スライディングウィンドウによる密集パターンの完全列挙（厳密解）
- 問題設定: 1トランザクション = 1アイテムセット（バスケット構造なし）

### 1.2 新論文（Phase 1 拡張）の主貢献
- **提案手法**: バスケット内共起のみを真の共起と定義することで偽共起を排除
- **実証**: 合成データ（Stage A）で λ_baskets に比例して SPR が増加することを示し、Phase 1 が SPR=0 を維持することを確認
- **位置づけ**: Apriori-window の上位互換

### 1.3 既存論文との差分
| 側面 | DSAA2025 | 新論文 |
|------|---------|-------|
| トランザクション構造 | 1 txn = 1バスケット（固定） | 1 txn = 複数バスケット |
| 共起の定義 | トランザクション内 | バスケット内 |
| 評価指標 | F1-score | SPR + observed_spurious + 実行時間 |

---

## 2. 論文構成（推奨）

```
1. Introduction
2. Related Works
3. Problem Definition
   3.1 バスケット構造付きトランザクションデータの定義
   3.2 真の共起・偽共起の定義（true_support / txn_support / spurious）
4. Proposed Method（Phase 1）
   4.1 従来法の問題
   4.2 バスケット構造対応 Apriori-window アルゴリズム
   4.3 反単調性の証明
5. Experiments
   5.1 評価指標（SPR, observed_spurious）
   5.2 合成データ実験（Stage A）
   5.3 実データ実験（Stage B）※実施後に追加
6. Conclusion
```

---

## 3. 各セクションの執筆ガイド

### 3.1 Abstract（150〜250語）
1. **背景**: なぜこの問題が重要か
2. **問題**: 既存手法の限界
3. **提案**: Phase 1 が何をするか
4. **結果**: SPR=0 を維持

**注意**: 受動態より能動態（"We propose..."）、数値を入れると説得力が増す

### 3.2 Problem Definition の定義すべき概念
```
定義1: バスケット (Basket)
定義2: バスケット構造付きトランザクション (ts, {B_1, ..., B_n})
定義3: バスケット内共起（真の共起）
定義4: トランザクション内共起（従来法の共起）
定義5: true_support / txn_support / spurious
定義6: Basket-aware Dense Pattern
```
- 定義は `\begin{definition}` 環境で書く
- 定義の後に必ず具体例を入れる（牛乳-パン / ビール-ポテチの例）

### 3.3 Experiments の書き方
```
5.1 生成モデルの説明（Poisson モデル、λ_baskets の意味）
5.2 実験 A1（λ_baskets sweep: N=10000, G=10, λ=1.0/1.5/2.0/3.0/5.0, 5 seeds）
5.3 実験 A2（G sweep: λ=2.0, G=3/5/10/20/50）
5.4 実験 A3（スケーラビリティ: N=1K/10K/100K/1M）
```
- 「Phase 1 は SPR=0 を維持する」を強く主張する（主貢献の証明）

---

## 4. LaTeX 執筆ルール

### 4.1 ファイル構成
```
<論文ディレクトリ>/
  main.tex, refs.bib
  sec/01_intro.tex, 02_related_works.tex, ...
  alg/, fig/, table/
```

### 4.2 よく使う環境
```latex
\begin{definition}[名前] ... \end{definition}
\begin{theorem} ... \end{theorem}
\begin{proof} ... \end{proof}
\begin{algorithm}\caption{...}\begin{algorithmic}[1]...\end{algorithmic}\end{algorithm}
% 表: キャプションは上、図: キャプションは下
```

### 4.3 数式スタイル
- インライン: `$...$`
- 番号付き式: `\begin{equation}...\end{equation}`
- 複数行: `\begin{IEEEeqnarray}{rCl}...\end{IEEEeqnarray}`

---

## 5. 用語の統一

| 概念 | 論文中の英語表記 |
|------|---------------|
| バスケット | basket |
| 偽共起 | spurious co-occurrence |
| 偽共起パターン率 | Spurious Pattern Rate (SPR) |
| バスケット内共起 | intra-basket co-occurrence |
| Phase 1 / バスケット対応版 | Basket-aware Apriori-window |

---

## 6. 参照ファイル

| ファイル | 用途 |
|---------|------|
| `paper/target/dsaa2025/sec/*.tex` | 既存論文セクション（流用・参考元） |
| `experiments/doc/experiment_design.md` | 実験設計 |
| `apriori_window_suite/src/` / `apriori_window_suite/python/` | アルゴリズム実装（疑似コード参照） |
| `experiments/results/` | 実験結果データ（実験完了後）|
| `experiments/registry/experiments.csv` | 実験台帳（実行済み条件・seed の確認） |
