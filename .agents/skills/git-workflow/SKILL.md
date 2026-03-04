---
name: git-workflow
description: apriori_window_suite における安全なブランチ管理・コミット分割・PR 作成。新機能実装後のコミット / PR 提出前チェック / push 前テスト確認に使う。
---

# Skill: git-workflow

## 0. Purpose

- **このSkillが解くタスク**: apriori_window_suite における安全なブランチ管理・コミット分割・PR 作成
- **使う場面**: 新機能実装後のコミット / PR 提出前のチェック / ブランチ作成 / マージ準備
- **できないこと（スコープ外）**: CI/CD パイプラインの変更・リベース・タグ付け

---

## 1. Inputs

### 1.1 Required

- **変更の種類**: 何をしたか（prototype / rust-port / test-add / doc-update / bugfix のいずれか）
- **変更ファイルのリスト**: `git status` で確認した未ステージのファイル一覧

### 1.2 Optional

- **既存ブランチ名**: 作業ブランチが決まっている場合（例: `feature/add-doe-relation`）
- **PR のターゲット**: デフォルトは `main`

### 1.3 Missing info policy

- コミットメッセージの意図が不明な場合は作業を止めて質問する（推測でコミットしない）
- ファイルの変更内容が不明な場合は `git diff` で確認してから着手する

---

## 2. Outputs

### 2.1 Deliverables

- ステージされ、適切なメッセージでコミットされた変更
- push 済みのブランチ（PR 作成時のみ）
- PR 本文（変更点・テスト件数・影響範囲を含む）

### 2.2 コミットメッセージ形式

```
<type>: <要点を1行で>

- 変更点1
- 変更点2
（3行以内）
```

| type | 使う場面 |
|------|---------|
| `feat` | 新機能の追加（Python prototype または Rust port） |
| `test` | テストの追加・修正のみ |
| `docs` | ドキュメント・impl_log.md の更新のみ |
| `fix` | バグ修正 |
| `refactor` | 動作変更なしのリファクタリング |

### 2.3 PR 本文形式

```markdown
## 変更点

- （箇条書き）

## テスト結果

- Rust: N passed（cargo test）
- Python Phase 1: N passed
- Python Phase 2: N passed

## 影響範囲

- 変更したモジュール:（一覧）
- 変更していないモジュール:（一覧）
```

---

## 3. Procedure

### 3.1 ブランチ作成（新機能のとき）

1. `main` から派生した `feature/<機能名>` ブランチを作る
   ```sh
   git checkout main && git pull origin main
   git checkout -b feature/<機能名>
   ```
2. ブランチ名は小文字・ハイフン区切りにする（例: `feature/add-eod-relation`）

### 3.2 push 前チェック（必須）

以下をすべて通過してから `git add` する:

```sh
# Rust（apriori_window_suite/ 内から実行）
cd apriori_window_suite && cargo test

# Python（リポジトリルートから実行）
python3 -m pytest apriori_window_suite/python/tests/ -v
```

テストが 1 件でも失敗している場合はコミットしない。

### 3.3 コミット分割ルール

**1 コミット = 1 意図**。以下の種類は必ず別コミットにする:

| コミット | ステージするファイル |
|----------|-------------------|
| Python prototype | `python/apriori_window_basket.py` または `python/event_correlator.py` |
| Rust port | `src/*.rs` |
| テスト追加 | `python/tests/test_*.py` と `src/*.rs`（`#[test]` の追加分） |
| ドキュメント更新 | `doc/impl_log.md`, `doc/README.md`, `CLAUDE.md` |

### 3.4 コミット手順

```sh
# 変更差分の確認
git diff

# ステージ（対象ファイルのみ指定する。git add . は使わない）
git add apriori_window_suite/src/correlator.rs

# コミット
git commit -m "feat: DFE 関係の Rust 実装を追加"
```

### 3.5 PR 作成

```sh
# push
git push -u origin feature/<機能名>

# PR 作成（gh CLI）
gh pr create --title "<要点>" --body "$(cat <<'EOF'
## 変更点
- ...

## テスト結果
- Rust: N passed
- Python Phase 1: N passed
- Python Phase 2: N passed

## 影響範囲
- 変更したモジュール: ...
- 変更していないモジュール: ...
EOF
)"
```

---

## 4. Quality Gates

- **テスト全パス**: push 前に `cargo test` と `pytest` が全 passed であること
- **コミット分割**: Python / Rust / テスト / ドキュメントが別コミットになっていること
- **コミットメッセージ**: `<type>: <要点>` 形式で意図が 1 行で分かること
- **ステージ対象の正確性**: `git add .` を使わず、変更ファイルを個別指定していること
- **PR の記載**: 変更点・テスト件数（実測値）・影響範囲が含まれていること
- **テスト件数の下限**: Rust 54+、Python Phase 1 24+、Python Phase 2 40+ を維持していること

---

## 5. Failure Modes & Fixes

- **失敗例1: テスト失敗のままコミット** / 回避策: § 3.2 のコマンドをコピペして必ず実行する
- **失敗例2: 複数意図が 1 コミットに混在** / 回避策: ファイルを 1 つずつ `git add <path>` する
- **失敗例3: main に直接コミット** / 回避策: 作業開始時に `git branch` で現在のブランチを確認する
- **失敗例4: PR 本文のテスト件数が実測と違う** / 回避策: `cargo test` / `pytest` を PR 作成直前に再実行して件数を確認する
- **失敗例5: force push で upstream を上書き** / 回避策: force push は絶対に使わない

---

## 6. Evaluation

- **合格ライン**: テスト全パス + コミット分割済み + PR 本文に実測テスト件数が記載されている
- **重大欠陥（即NG）**:
  - テストが 1 件でも失敗している状態で push している
  - `main` ブランチに直接コミット・push している
  - PR 本文にテスト結果が記載されていない

---

## 7. Execution Notes

- **ブランチ確認コマンド**:
  ```sh
  git branch           # 現在のブランチ一覧
  git status           # 未ステージのファイル確認
  git diff             # 変更内容確認
  git log --oneline -5 # 直近5コミットの確認
  ```
- **テスト実行コマンド**:
  ```sh
  cd apriori_window_suite && cargo test
  python3 -m pytest apriori_window_suite/python/tests/ -v
  ```
- **PR 確認コマンド**:
  ```sh
  gh pr list           # 既存 PR の確認
  gh pr view           # 現在の PR 内容確認
  ```
