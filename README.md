# apriori_window

バスケット構造対応 Apriori + スライディングウィンドウによる密集アイテムセット区間検出と、外部イベントとの時間的関係列挙のための研究開発リポジトリ。

## 概要

従来の Apriori は「1トランザクション = 1バスケット」を前提とするため、同一時間帯に異なるユーザーの購買が1トランザクションに集約される環境では偽共起が生じる。本手法はトランザクションが複数バスケットを持てる構造に拡張し、**同一バスケット内の共起のみを真の共起**と定義することで、この問題を解決する。

- **Phase 1**: バスケット対応 Apriori + スライディングウィンドウで密集アイテムセット区間を検出
- **Phase 2**: 検出された密集区間と外部イベントの時間的関係（DFE / EFD / DCE / ECD / DOE / EOD）を列挙
- **Phase 3**: 実データ（Dunnhumby / UCI Online Retail II）での検証 ← 現在進行中

## リポジトリ構造

```
apriori_window/
├ apriori_window_suite/   メイン実装（Rust + Python 二重実装）
├ apriori_window_original/ バスケットなし版リファレンス実装
├ baselines/              比較手法（LPFIM / LPPM / PPFPM 等）
├ benchmarks/             ベンチマーク定義（スイート・指標・プロトコル）
├ experiments/            実験スクリプト・設定・結果
├ paper/                  論文原稿・提出物・再現性資料
├ dataset/                実験データセット（一部 git 管理外）
├ tools/                  開発補助スクリプト
└ runs/                   実行結果生データ（gitignore 対象）
```

## クイックスタート

### ビルド・テスト

```sh
# Rust ビルド
cd apriori_window_suite && cargo build --release

# Rust テスト（54 lib + 4 E2E）
cd apriori_window_suite && cargo test

# Python テスト（24 + 40 件）
python3 -m pytest apriori_window_suite/python/tests/ -v
```

### 実行

```sh
# Phase 1 — 密集アイテムセット区間検出
cd apriori_window_suite && cargo run -- phase1 data/settings.json

# Phase 2 — イベント時間的関係付け
cd apriori_window_suite && cargo run -- phase2 data/settings_phase2.json
```

### 実験（Stage A 合成データ）

```sh
python3 experiments/gen_synthetic.py    # 合成データ生成
python3 experiments/run_phase1.py       # Phase1 vs 従来法 比較
python3 experiments/analyze_results.py  # 結果集計
```

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | AI エージェント向けプロジェクトガイド |
| [`AGENTS.md`](AGENTS.md) | エージェント役割定義 |
| [`apriori_window_suite/doc/OVERVIEW.md`](apriori_window_suite/doc/OVERVIEW.md) | 実装詳細・API |
| [`baselines/OVERVIEW.md`](baselines/OVERVIEW.md) | 比較手法一覧・入手元・注意点 |
| [`benchmarks/OVERVIEW.md`](benchmarks/OVERVIEW.md) | ベンチマーク設計 |
| [`experiments/doc/experiment_design.md`](experiments/doc/experiment_design.md) | 実験設計書（Stage A/B/C）|
| [`paper/reproducibility_appendix/`](paper/reproducibility_appendix/) | 再現性情報 |

## 実装言語

- **Rust** (`apriori_window_suite/src/`) — 高速実行用
- **Python** (`apriori_window_suite/python/`) — プロトタイプ・実験スクリプト

## ライセンス

MIT
