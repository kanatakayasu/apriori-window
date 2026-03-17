# apriori_window

Apriori + スライディングウィンドウによる密集アイテムセット区間検出と、サポート変動の外部イベント帰属のための研究開発リポジトリ。

## 概要

Apriori とスライディングウィンドウを組み合わせ、頻出アイテムセットが密集して出現する時間区間を検出する。さらに、サポート時系列の変化点を検出し、その変動がどの外部イベント（セール、祝日、キャンペーン等）に起因するかを統計的に特定する。

- **Phase 1**: Apriori + スライディングウィンドウで密集アイテムセット区間を検出し、サポート時系列を出力
- **Phase 2**: サポート時系列の変化点検出 → 外部イベントへの帰属スコアリング → 置換検定による有意性判定

## リポジトリ構造

```
apriori_window/
├ apriori_window_suite/   メイン実装（Rust + Python 二重実装）
├ apriori_window_original/ 旧版リファレンス実装
├ doc/                    設計文書・関連研究サーベイ
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

# Rust テスト
cd apriori_window_suite && cargo test

# Python テスト
python3 -m pytest apriori_window_suite/python/tests/ -v
```

### 実行

```sh
# Phase 1 — 密集アイテムセット区間検出 + サポート時系列出力
cd apriori_window_suite && cargo run -- phase1 data/settings.json

# Phase 2 — イベント帰属
python3 apriori_window_suite/python/event_attribution.py data/settings_phase2.json
```

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | AI エージェント向けプロジェクトガイド |
| [`AGENTS.md`](AGENTS.md) | エージェント役割定義 |
| [`doc/temporal_relation_pipeline.md`](doc/temporal_relation_pipeline.md) | Event Attribution Pipeline 設計書 |
| [`doc/related_work_survey.md`](doc/related_work_survey.md) | 関連研究サーベイ |
| [`apriori_window_suite/doc/OVERVIEW.md`](apriori_window_suite/doc/OVERVIEW.md) | 実装詳細・API |

## 実装言語

- **Rust** (`apriori_window_suite/src/`) — 高速実行用
- **Python** (`apriori_window_suite/python/`) — プロトタイプ・実験スクリプト

## ライセンス

MIT
