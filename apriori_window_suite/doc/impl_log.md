# 実装ログ (impl_log.md)

実装完了後に追記する変更履歴。1エントリ = 1コミット意図。

## フォーマット

```
### YYYY-MM-DD — <変更タイトル>
- **対象**: 変更したファイル / モジュール
- **内容**: 何を変更したか（1〜3行）
- **テスト**: 追加・変更したテスト名
- **関連コミット**: <git short hash>
```

---

## ログ

### 2026-04-02 — Rust完全移行: ベースライン・合成データ生成・評価モジュール追加 + CLIサブコマンド
- **対象**: `src/baselines.rs`（新規）, `src/synth.rs`（新規）, `src/evaluate.rs`（新規）, `src/main.rs`（clap CLI再設計）, `src/lib.rs`（モジュール登録）, `Cargo.toml`（clap依存追加）
- **内容**: 5手法ベースライン（Wilcoxon/CausalImpact/ITS/EventStudy/ECA）をRustで実装（rayon並列化・O(N) two-pointer）。合成データ生成・評価指標もRust移植。CLIにphase1/run-experiment/run-ex1/run-ex3サブコマンド追加。N=1,000,000 × 10 seeds での実験が2255秒で完了確認。
- **テスト**: 63 lib/main tests（全pass）
- **関連コミット**: (main branch)

### 2026-03-01 — Phase 1 + Phase 2 統合クレート初期実装
- **対象**: `apriori_window_suite/` クレート全体
- **内容**: Phase 1（バスケット対応 Apriori-window）と Phase 2（イベント時間的関係）を統合
- **テスト**: 54 lib tests + 4 E2E tests
- **関連コミット**: (dev_takayasu ブランチ初期)
