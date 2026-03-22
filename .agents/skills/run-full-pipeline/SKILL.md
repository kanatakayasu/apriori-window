---
name: run-full-pipeline
description: 1 論文を Phase 1〜6 まで一気通貫で実行するオーケストレーションスキル。エージェントチームの編成・並列実行・進捗管理を行う。
---

# Skill: run-full-pipeline

## 0. Purpose

- **このSkillが解くタスク**: 1 論文の Phase 1 (Research) 〜 Phase 6 (Pages) までの全工程を自律的に完走する
- **使う場面**: 新論文の着手時に全フェーズを一括実行
- **できないこと**: 複数論文の同時オーケストレーション（それは Wave プロンプトで行う）

---

## 1. Inputs

### 1.1 Required

- **論文 ID**: MASTER_PROMPT.md の paper_id
- **ブランチ名**: `paper/{paper_id}` 形式

### 1.2 Loaded from MASTER_PROMPT.md

以下は論文定義から自動取得:
- title, title_ja, venue, difficulty
- research_areas, concepts_to_define
- core_implementation, experiments
- dependencies, cites, cited_by

---

## 2. Execution Flow

```
┌─────────────────────────────────────────────────┐
│                 PRE-FLIGHT                       │
│  1. ブランチ作成 (main → paper/{ID})             │
│  2. ディレクトリ構造作成                          │
│  3. README.md (ステータスダッシュボード) 作成      │
│  4. 依存論文の確認                               │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│              PHASE 1: RESEARCH                   │
│  [並列] Researcher: literature_review.md          │
│  [並列] Researcher: gap_analysis.md               │
│  [後続] BibTeX 生成: refs.bib                     │
│  → コミット: "research: 論文{ID} 文献調査完了"     │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│           PHASE 2: FORMALIZATION                 │
│  Architect: formalization.md                     │
│  → LaTeX 化: sec/03_problem_definition.tex       │
│  → コミット: "research: 論文{ID} 定式化完了"      │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│          PHASE 3: IMPLEMENTATION                 │
│  [並列] Coder: Python プロトタイプ               │
│  [並列] Coder: Python テスト                     │
│  [後続] Reviewer: pytest 実行                    │
│  [後続] Coder: Rust 移植                         │
│  [後続] Reviewer: cargo test + 一致確認          │
│  → コミット: "feat: 論文{ID} Python実装"          │
│  → コミット: "feat: 論文{ID} Rust移植"            │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│           PHASE 4: EXPERIMENTS                   │
│  Experimenter: 実験設計書                        │
│  [並列] Experimenter: 合成データ実験             │
│  [並列] Experimenter: 実データ実験               │
│  [並列] Experimenter: アブレーション             │
│  [後続] Experimenter: 結果分析・図表生成         │
│  → コミット: "experiments: 論文{ID} 実験完了"     │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│          PHASE 5: PAPER WRITING                  │
│  [並列] Writer: Introduction + Related Work      │
│  [並列] Writer: Problem Def + Proposed Method    │
│  [並列] Writer: Experiments + Conclusion         │
│  [後続] Reviewer: 全体統合・整合性チェック       │
│  → コミット: "paper: 論文{ID} 原稿完成"           │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│           PHASE 6: PAGES & POLISH                │
│  Designer: LP 作成                               │
│  Designer: インデックスページ更新                │
│  → コミット: "pages: 論文{ID} LP作成"             │
└──────────────┬──────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────┐
│              POST-FLIGHT                         │
│  1. README.md ステータス更新 (全 ✅)              │
│  2. PROGRESS.md 更新                             │
│  3. main にマージ                                │
│  4. gh-pages にデプロイ                          │
└─────────────────────────────────────────────────┘
```

---

## 3. Error Handling

### 質問・ユーザーアクション

- 作業中にユーザー判断が必要な事項: `PENDING_QUESTIONS.md` に記録して続行
- ユーザーアクション（データDL等）が必要: `PENDING_ACTIONS.md` に記録し、回避策で仮進行

### フェーズ失敗

| 失敗 | 対応 |
|------|------|
| テスト失敗 | `/debug-test` スキルで原因特定・修正 |
| 実験結果が期待と異なる | パラメータ調整して再実行（3回まで） |
| 論文のページ数不足 | 実験追加 or 理論的考察を深掘り |
| gh-pages デプロイ失敗 | コンフリクト解消して再試行 |

### 停止条件（これが発生したら PENDING_QUESTIONS.md に記録して仮続行）

1. アルゴリズムの正当性に根本的な疑義がある
2. 必要なデータセットが入手不能で代替もない
3. 依存論文の結果が本論文の前提を覆す

---

## 4. Quality Gates (Cumulative)

| Phase | 完了条件 | 確認コマンド |
|-------|---------|------------|
| 1 | literature_review.md: 20+ 論文, gap_analysis.md: 3+ ギャップ | `wc -l paper/{ID}/research/*.md` |
| 2 | formalization.md: 全概念定義済み, 主定理に証明 | LaTeX コンパイル成功 |
| 3 | Python テスト 10+ passed, Rust テスト passed, 既存テスト未破壊 | `pytest -v` + `cargo test` |
| 4 | 3+ 実験 × 5+ seed, 図表生成済み, analysis.md 完成 | 結果 JSON 存在確認 |
| 5 | 8+ ページ, 20+ 参考文献, Abstract 150-250 語 | `texcount main.tex` |
| 6 | LP 正常表示, インデックスからリンク通る | ブラウザ確認 |

---

## 5. Commit Convention

```
research: 論文{ID} 文献調査完了
research: 論文{ID} 定式化完了
feat: 論文{ID} Python プロトタイプ
test: 論文{ID} Python テスト追加
feat: 論文{ID} Rust 移植
test: 論文{ID} Rust テスト追加
experiments: 論文{ID} 合成データ実験
experiments: 論文{ID} 実データ実験
experiments: 論文{ID} 結果分析
paper: 論文{ID} Introduction + Related Work
paper: 論文{ID} Problem Definition + Method
paper: 論文{ID} Experiments + Conclusion
paper: 論文{ID} 原稿統合・最終版
pages: 論文{ID} LP 作成
docs: 論文{ID} README・進捗更新
```
