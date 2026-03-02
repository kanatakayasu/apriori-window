# Skill: write-paper

## 0. Purpose

- **このSkillが解くタスク**: バスケット構造対応 Apriori-window（Phase 1）に関する学術論文の執筆・改訂
- **使う場面**: 新セクションの草稿作成 / 既存セクションの改訂 / 実験結果の文章化 / 投稿テンプレへの適合
- **前提知識**: `DSAA2025/` の既存論文（Apriori-window + Plant Model）が先行研究として存在する。新論文はその「バスケット構造拡張」を主貢献として追加する。
- **できないこと（スコープ外）**: 実験の実行・データ解析・コード実装（それぞれ `run-experiment.md` / `impl-feature.md` を使う）

---

## 1. 研究の位置づけ

### 1.1 先行論文（DSAA2025）の主貢献
- **Apriori-window**: スライディングウィンドウによる密集パターンの完全列挙（厳密解）
- **Plant Model**: 群知能による密集区間の近似探索（ヒューリスティック）
- 問題設定: 1トランザクション = 1アイテムセット（バスケット構造なし）

### 1.2 新論文（Phase 1 拡張）の主貢献
- **従来法の問題**: 同一時間帯の複数の独立した購買（バスケット）を1トランザクションに集約すると、異なるバスケット由来のアイテムが誤って「共起」とみなされる（偽共起）
- **提案手法（Phase 1）**: トランザクションが複数バスケットを持てる構造に拡張し、バスケット内共起のみを真の共起と定義することで偽共起を排除
- **実証**: 合成データ（Stage A）で λ_baskets に比例して SPR が増加することを示し、Phase 1 が SPR=0 を維持することを確認
- **位置づけ**: Apriori-window の入力モデルを拡張した研究であり、先行論文の完全上位互換

### 1.3 既存論文との差分（新論文で書き分けること）
| 側面 | DSAA2025 | 新論文 |
|------|---------|-------|
| トランザクション構造 | 1 txn = 1バスケット（固定） | 1 txn = 複数バスケット |
| 共起の定義 | トランザクション内 | バスケット内（同一購買イベント内） |
| 問題設定 | 密集パターンの抽出 | **偽共起を排除した**密集パターンの抽出 |
| 評価指標 | F1-score（パターン識別精度） | SPR + observed_spurious + 実行時間 |
| 実験データ | 実データのみ | 合成データ（SPR 検証）+ 実データ |

---

## 2. 論文構成（推奨）

```
1. Introduction
   - 背景: 取引データのバスケット構造と偽共起の問題
   - 問題提起: 従来の Apriori-window が抱える偽共起の課題
   - 主貢献: Phase 1 による解決
   - 論文構成の案内

2. Related Works
   - 頻出パターンマイニング（Apriori, FP-Growth, ECLAT）
   - 時間的密集パターンマイニング（LPFIM, LPPM, PFPM）← DSAA2025 と重複可
   - バスケット構造 / トランザクション構造を考慮した手法（差別化点として強調）

3. Problem Definition
   3.1 バスケット構造付きトランザクションデータの定義
   3.2 真の共起・偽共起の定義（true_support / txn_support / spurious）
   3.3 解くべき問題の定式化

4. Proposed Method（Phase 1）
   4.1 従来法の問題の形式的説明
   4.2 バスケット構造対応 Apriori-window のアルゴリズム
   4.3 反単調性の証明（DSAA2025 の証明を拡張）
   4.4 計算量の分析

5. Experiments
   5.1 評価指標（SPR, observed_spurious）
   5.2 合成データ実験（Stage A: SPR の実証）
   5.3 実データ実験（Stage B: UCI Online Retail II）※実施後に追加
   5.4 考察

6. Conclusion
   - まとめ・主結果
   - 限界と今後の課題（Phase 2 の言及など）
```

---

## 3. 各セクションの執筆ガイド

### 3.1 Abstract（150〜250語）
以下の4要素を1〜2文ずつ書く：
1. **背景**: なぜこの問題が重要か（取引データのバスケット構造、偽共起の問題）
2. **問題**: 既存手法が何を見逃しているか（1トランザクション=1バスケット仮定）
3. **提案**: Phase 1 が何をするか（バスケット内共起限定による偽共起排除）
4. **結果**: 何を示したか（SPR で定量評価、Phase 1 は SPR=0 を維持）

**書き方の注意**:
- 受動態よりも能動態で書く（"We propose..." "Our method..."）
- 数値を入れると説得力が増す（例: "reduces spurious patterns by X%"）
- DSAA2025 の Abstract を参考に同一トーンで書く

### 3.2 Introduction
**構成（逆ピラミッド構造）**:
1. 取引データ分析の重要性（広い背景）
2. 密集パターン抽出の意義（DSAA2025 の問題設定を簡潔に引用）
3. バスケット構造の現実的な存在（e.g., 同一日付に複数顧客が購買）
4. 従来の Apriori-window が見落とすケースの具体例（牛乳-パン / ビール-ポテチ例）
5. 提案手法（Phase 1）の概要と主貢献
6. 論文構成の案内

**書き方の注意**:
- 具体例は読者に直感的に理解させるために重要（Section 1.1 の例示をそのまま使える）
- DSAA2025 の Introduction と差別化できるよう、バスケット構造の話題から入る
- 主貢献は箇条書きで明示すると読みやすい

### 3.3 Related Works
**カバーすべきトピック**:
1. 頻出パターンマイニング（Apriori, FP-Growth）← 既存論文から流用可
2. 時間的・局所的パターンマイニング（LPFIM, LPPM, PFPM, PPFPM）← 既存論文から流用可
3. **バスケット構造関連**（新論文で追加すべき）:
   - Inter-transaction association rules
   - Multi-relational data mining
   - Market basket analysis の現実的なシナリオ

**書き方の注意**:
- 既存論文（DSAA2025）の Related Works を土台に、バスケット構造関連節を追加する
- 「既存手法はバスケット構造を考慮していない」という差別化ポイントを明確に述べる

### 3.4 Problem Definition
**定義すべき概念**（DSAA2025 の定義を拡張する形で）:

```
定義1: バスケット (Basket)
  1回の独立した購買イベント。アイテムの集合。

定義2: バスケット構造付きトランザクション (Basket-structured Transaction)
  (ts, {B_1, B_2, ..., B_n}) のペア。
  ts: タイムスタンプ、B_i: バスケット（アイテムの集合）

定義3: バスケット内共起 (Intra-basket co-occurrence) ← 真の共起
  アイテムセット P が同一バスケット内に含まれること。

定義4: トランザクション内共起 (Intra-transaction co-occurrence) ← 従来法の共起
  P のすべてのアイテムが（バスケット横断で）同一トランザクション内に含まれること。

定義5: true_support(P) / txn_support(P) / spurious(P)
  (experiment_design.md Section 1.2.3 の定義をそのまま使う)

定義6: Basket-aware Dense Pattern
  バスケット内共起のみに基づく dense pattern
```

**書き方の注意**:
- 定義は数式で厳密に書く（LaTeX の `\begin{definition}` 環境を使う）
- 定義の後に必ず具体例を入れる（牛乳-パン / ビール-ポテチの例）
- DSAA2025 の定義（Def 1〜3）との対応を明示する

### 3.5 Proposed Method（Phase 1）
**構成**:
1. 従来法の問題（形式的な説明）: txn_support > true_support になるケース
2. アルゴリズムの概要（疑似コード）
3. 重要な実装の詳細:
   - `compute_item_basket_map` の役割
   - バスケット粒度での共起タイムスタンプ計算
   - `basket_ids_to_transaction_ids` の意図的な重複設計
4. 反単調性の証明（バスケット内共起でも成立することを示す）
5. 既存 Apriori-window との計算量の差分分析

**疑似コードのポイント**:
- `DSAA2025/alg/` の既存疑似コードを参考に同一スタイルで書く
- バスケット処理の追加部分を強調（`\textbf{}` 等）

**反単調性の証明**:
- バスケット内共起は真の共起であり、その superset の basket-level support も単調非増加になることを示す
- DSAA2025 の証明（`sec/04_proposed_method.tex`）を拡張する

### 3.6 Experiments
**合成データ実験（Stage A）の書き方**:

```
5.1 生成モデルの説明
    - Poisson モデルの生成プロセス（λ_baskets の意味）
    - Ground Truth (SPR) の定義

5.2 実験 A1（λ_baskets sweep）
    - 目的: SPR が λ に比例して増加することの実証
    - 設定: N=10000, G=10, λ=1.0/1.5/2.0/3.0/5.0, 5 seeds
    - 結果表 or 図（λ vs mean SPR）
    - 結果の解釈: "Phase 1 maintains SPR=0 regardless of λ"

5.3 実験 A2（G sweep）
    - 目的: カテゴリ構造が偽共起発生率に与える影響
    - 設定: λ=2.0, G=3/5/10/20/50
    - 結果と解釈

5.4 実験 A3（スケーラビリティ）
    - 目的: 実用的な処理速度の確認
    - 設定: N=1K/10K/100K/1M
    - 結果表（N vs elapsed_ms）
```

**結果の書き方の注意**:
- 数値は表または折れ線グラフで示す
- 表のキャプションは上、図のキャプションは下
- 「Phase 1 は SPR=0 を維持する」を強く主張する（これが主貢献の証明）
- 実行時間は N に対して対数スケールでプロットすると見やすい

### 3.7 Conclusion
**構成**:
1. 主結果の要約（1〜2文）
2. 主貢献の再確認（Phase 1 によって偽共起を排除できた）
3. 限界（PowerLaw モデルの実験未実施、UCI データの実験未実施など）
4. 今後の課題（Phase 2 との統合、Rust 実装のスケーラビリティ評価など）

---

## 4. LaTeX 執筆ルール

### 4.1 ファイル構成（DSAA2025 と同じ構成を踏襲）
```
<論文ディレクトリ>/
  main.tex              ← \input{} でセクションを読み込む
  refs.bib              ← BibTeX 参考文献
  sec/
    01_intro.tex
    02_related_works.tex
    03_problem_definition.tex
    04_proposed_method.tex
    05_experiment.tex
    06_conclusion.tex
  alg/                  ← 疑似コード
  fig/                  ← 図（PNG/PDF）
  table/                ← 表（別ファイルで管理するなら）
```

### 4.2 よく使う環境
```latex
% 定義
\begin{definition}[名前]
...
\end{definition}

% 定理・証明
\begin{theorem} ... \end{theorem}
\begin{proof} ... \end{proof}

% 疑似コード（DSAA2025 と同様）
\begin{algorithm}
\caption{...}
\begin{algorithmic}[1]
...
\end{algorithmic}
\end{algorithm}

% 表（IEEE スタイル）
\begin{table}[t]
  \centering
  \caption{...}  % 表は上にキャプション
  \begin{tabular}{|c|c|c|}
  ...
  \end{tabular}
\end{table}

% 図
\begin{figure}[t]
  \includegraphics[width=\linewidth]{fig/...}
  \caption{...}  % 図は下にキャプション
  \label{fig:...}
\end{figure}
```

### 4.3 数式スタイル
- インライン: `$...$`
- 番号付き式: `\begin{equation}...\end{equation}`
- 複数行: `\begin{IEEEeqnarray}{rCl}...\end{IEEEeqnarray}`（DSAA2025 の形式）

### 4.4 参考文献
- `refs.bib` に BibTeX 形式で追加
- DSAA2025 の `refs.bib` を共通ベースとして使う
- 新論文で追加すべき文献:
  - バスケット構造関連の論文（見つかり次第追加）
  - UCI Online Retail II データセットの引用

---

## 5. 執筆ワークフロー

```
Step 1  Problem Definition の草稿を書く（定義が固まれば他セクションが書きやすくなる）
Step 2  Proposed Method の疑似コードと証明を書く
Step 3  Experiments の表・図の配置を決め、結果を埋める（実験完了後）
Step 4  Introduction を書く（他セクションが固まってから書くと一貫性が保てる）
Step 5  Related Works を書く（DSAA2025 を土台に、バスケット関連節を追加）
Step 6  Abstract を書く（最後に書く）
Step 7  Conclusion を書く
Step 8  全体の読み直し（論理の流れ・用語の一貫性・数式番号・参考文献の確認）
Step 9  投稿先テンプレへの適合（ページ数制限・フォント・マージン等）
```

---

## 6. 主張すべき核心ポイント（論文全体を通じて一貫させる）

| ポイント | 根拠 | 使うセクション |
|---------|------|-------------|
| 偽共起は λ_baskets に比例して増加する | 実験 A1 の SPR グラフ | Introduction, Experiments |
| Phase 1 は SPR=0 を維持する | 定義より自明 + 実験で確認 | Abstract, Introduction, Proposed Method, Experiments |
| バスケット内共起にも反単調性が成立する | 証明 | Proposed Method |
| Phase 1 は従来 Apriori-window の上位互換 | λ=1 のとき Phase 1 = 従来法 | Introduction, Proposed Method |
| 実用的な処理速度を維持する | 実験 A3 の実行時間 | Experiments, Conclusion |

---

## 7. 用語の統一

| 概念 | 論文中の英語表記 |
|------|---------------|
| バスケット | basket |
| バスケット構造付きトランザクション | basket-structured transaction |
| 偽共起 | spurious co-occurrence |
| 偽共起パターン率 | Spurious Pattern Rate (SPR) |
| バスケット内共起 | intra-basket co-occurrence |
| トランザクション内共起 | intra-transaction co-occurrence |
| 真のサポート | true support |
| 従来法 | conventional method / baseline |
| Phase 1 / バスケット対応版 | Basket-aware Apriori-window |

---

## 8. よくある失敗と対策

| 失敗 | 対策 |
|------|------|
| Introduction で貢献が不明瞭 | 箇条書きで "Our contributions are:" と明示する |
| 定義が直感的でない | 必ず具体例（牛乳-パンの例）を定義の直後に入れる |
| 実験の設定説明が不足 | 再現可能なレベルでパラメータを全記載する |
| Related Works が単なる羅列 | 各手法の「限界」を書き、提案手法との差別化を明示する |
| Conclusion が Introduction の繰り返し | 「限界」と「今後の課題」を必ず入れる |
| 数式と本文の乖離 | 数式の後に必ず「where X is...」と説明を入れる |

---

## 9. 参照ファイル

| ファイル | 用途 |
|---------|------|
| `DSAA2025/sec/*.tex` | 既存論文セクション（流用・参考元） |
| `DSAA2025/refs.bib` | 既存参考文献 |
| `apriori_window_suite/doc/experiment_design.md` | 実験設計（Section 5 の執筆に使う） |
| `apriori_window_suite/python/apriori_window_basket.py` | アルゴリズムの実装（疑似コード作成の参照元） |
| `experiments/results/A1_spr.csv` | 実験結果データ（実験完了後） |
