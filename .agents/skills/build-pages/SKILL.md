---
name: build-pages
description: GitHub Pages のランディングページ作成とデプロイ。論文ごとの LP + 全体インデックスページの構築。
---

# Skill: build-pages

## 0. Purpose

- **このSkillが解くタスク**: 論文ごとの GitHub Pages ランディングページ作成、全体インデックスの更新、gh-pages ブランチへのデプロイ
- **使う場面**: 論文の Phase 6 (Pages & Polish) / 全体インデックスの初期構築・更新
- **できないこと**: 論文の内容執筆・実験実行

---

## 1. Inputs

### 1.1 Required

- **論文 ID**: MASTER_PROMPT.md の paper_id
- **論文情報**: タイトル、著者、投稿先、Abstract、主要結果

### 1.2 Optional

- **図表**: 実験結果の図表（SVG / PNG）
- **ステータス**: 現在のフェーズ

---

## 2. Outputs

### 2.1 Deliverables

- **`paper/<ID>/pages/index.html`**: 論文 LP（単一 HTML、CSS/JS インライン）
- **`index.html`（更新）**: 全体インデックスページのカード追加

### 2.2 デプロイ先

```
gh-pages ブランチ:
├── index.html                    ← 全体インデックス（17 論文カード一覧）
├── paper/A/index.html            ← 論文 A の LP
├── paper/B/index.html            ← 論文 B の LP
└── ...
```

---

## 3. Procedure

### 3.1 論文 LP 作成

1. 論文の `manuscript/` から Abstract、主要結果、図表を収集
2. 統一テンプレートで HTML を生成:
   - ヘッダー: タイトル + 著者 + 投稿先バッジ + ステータスバッジ
   - サイドバーナビゲーション（スクロール連動）
   - セクション: 概要 / 手法 / 実験結果 / コード / 引用
   - フッター: リポジトリリンク + ライセンス
3. スタイルは既存 LP (`gh-pages:index.html`) と統一
4. レスポンシブ対応確認

### 3.2 インデックスページ

1. 全論文のカードを Tier 別にグルーピング
2. 各カードに表示:
   - 論文タイトル（日英）
   - ステータスバッジ（🔬📐💻🧪✍️📄✅）
   - 投稿先
   - 難度インジケーター
   - クリックで LP に遷移
3. 検索/フィルタ機能（JavaScript）

### 3.3 デプロイ

1. 作業ブランチから `gh-pages` ブランチに切り替え
2. HTML ファイルを配置
3. コミット + プッシュ
4. 元のブランチに戻る

---

## 4. Quality Gates

- HTML が W3C バリデーションを通過（重大エラーなし）
- モバイル表示で崩れない（viewport メタタグ設定済み）
- 外部 CDN/リソースに依存していない（CSS/JS 全てインライン）
- インデックスページから全論文 LP にリンクが通る
- ステータスバッジが `README.md` のダッシュボードと一致

---

## 5. Failure Modes & Fixes

- **失敗例1: gh-pages への push がコンフリクト** / 回避策: `git pull --rebase origin gh-pages` してから push
- **失敗例2: 図表が大きすぎて表示が遅い** / 回避策: SVG を使用、or PNG を 200KB 以下に圧縮
- **失敗例3: ステータスバッジが古い** / 回避策: デプロイ前に `PROGRESS.md` からステータスを再取得

---

## 6. Design Specifications

### カラーパレット

```css
:root {
  --primary: #2563eb;      /* Blue */
  --primary-dark: #1e40af;
  --accent: #f59e0b;       /* Amber */
  --bg: #ffffff;
  --bg-alt: #f8fafc;
  --text: #1e293b;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --success: #22c55e;
  --warning: #eab308;
  --info: #3b82f6;
}
```

### ステータスバッジ

| ステータス | バッジ | 色 |
|-----------|--------|-----|
| Research | 🔬 Research | `--info` |
| Formalization | 📐 Formalization | `--info` |
| Implementation | 💻 Implementation | `--warning` |
| Experiments | 🧪 Experiments | `--warning` |
| Writing | ✍️ Writing | `--accent` |
| Submitted | 📄 Submitted | `--primary` |
| Accepted | ✅ Accepted | `--success` |

### レスポンシブブレークポイント

```css
/* Mobile first */
@media (min-width: 768px) { /* Tablet */ }
@media (min-width: 1024px) { /* Desktop */ }
```
