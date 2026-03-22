---
name: formalize-theory
description: 問題定式化・定理証明・計算量解析。アルゴリズム手法論文の理論部分を構築する。
---

# Skill: formalize-theory

## 0. Purpose

- **このSkillが解くタスク**: 新しい密集区間マイニング手法の数学的定式化、定理の証明、計算量解析
- **使う場面**: 新論文の Phase 2 (Formalization) / Problem Definition・Proposed Method セクションの準備
- **できないこと**: 実装・実験・文献調査

---

## 1. Inputs

### 1.1 Required

- **定義すべき概念**: MASTER_PROMPT.md の `concepts_to_define` リスト
- **証明すべき性質**: 反単調性・計算量・正当性など
- **参照元**: 拡張の基となる既存定義（Apriori-Window の定義体系）

### 1.2 Optional

- **literature_review.md**: 既存手法の定式化パターンの参考
- **gap_analysis.md**: 差別化すべき理論的性質

### 1.3 Missing info policy

- アルゴリズムの意味論が不明な場合: 作業を止めて `PENDING_QUESTIONS.md` に記録し、最善の仮定で続行
- 証明が自明でない場合: 証明スケッチを書き、`[TODO: 厳密な証明]` マーカーを残す

---

## 2. Outputs

### 2.1 Deliverables

- **`formalization.md`**: 定義・定理・証明・計算量解析の Markdown 版
- **`sec/03_problem_definition.tex`**: LaTeX 版の定義・定理
- **`sec/04_proposed_method.tex`**: アルゴリズム記述・計算量証明の LaTeX

### 2.2 Structure

#### formalization.md

```markdown
# Formalization: {TOPIC}

## Notation
| 記号 | 意味 |
|------|------|
| D | トランザクションデータベース |
| P | パターン (アイテムセット) |
| s_P(l) | 窓位置 l でのパターン P のサポート |
| W | 窓幅 |
| θ | サポート閾値 |
| {NEW_SYMBOLS} | {NEW_MEANINGS} |

## Definition 1: {CONCEPT_1}
...

## Theorem 1: {PROPERTY_1}
**Statement**: ...
**Proof**: ...

## Algorithm
**Input**: ...
**Output**: ...
**Time Complexity**: O(...)
**Space Complexity**: O(...)
```

---

## 3. Procedure

1. **表記の確認**: 既存論文 (`paper/manuscript/sec/03_problem_definition.tex`) の表記を確認
2. **新概念の定義**: 既存概念の自然な拡張として定義（Definition 環境）
3. **具体例の追加**: 各定義の直後に具体例を 1 つ以上
4. **性質の定理化**: 反単調性・計算量・正当性を定理として記述
5. **証明の作成**: 形式的証明 or 証明スケッチ
6. **計算量解析**: ナイーブ vs 提案の両方の時間・空間計算量
7. **LaTeX 化**: Markdown の内容を LaTeX 環境に変換
8. **整合性チェック**: 既存定義との用語・表記の一貫性を確認

---

## 4. Quality Gates

- 全 `concepts_to_define` に対応する Definition が存在
- 各 Definition の直後に具体例
- 主定理に証明（最低でも証明スケッチ）
- 計算量がナイーブ・提案の両方で解析済み
- 既存論文の表記との一貫性（s_P, W, θ 等）
- LaTeX がコンパイル可能

---

## 5. Failure Modes & Fixes

- **失敗例1: 反単調性が成り立たない** / 回避策: 条件を緩和した弱い反単調性を定義、or 別の枝刈り戦略を設計
- **失敗例2: 計算量がナイーブと同じ** / 回避策: 特殊ケース（疎データ、小パターン）での改善を示す
- **失敗例3: 証明に致命的な欠陥** / 回避策: 反例を探索し、定理の前提条件を修正
