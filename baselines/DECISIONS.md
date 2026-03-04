# Decisions for Reproducible Implementation

## Status Legend

- `OPEN`: 未確定
- `DECIDED`: 決定済み

## Open Items

1. `LPFIM support定義`
- Status: `DECIDED`
- 候補A: 区間内比率ベース
- 候補B: 区間内件数ベース
- 推奨: 調査結果の推奨に従い「比率ベース」を採用し、`sigma` は `[0,1]` に正規化。
- 影響: LPFIM 出力件数・区間境界が大きく変わる。
- 決定: **候補B（区間内件数ベース）を採用**。

2. `PPFPM 実装の正`
- Status: `DECIDED`
- 候補A: 論文擬似コード逐語
- 候補B: 定義式 + 例 + PAMI実装を正とする
- 推奨: `候補B`。
- 影響: periodic-ratio 判定と再帰条件に差異が出る。
- 決定: **推奨どおり候補Bを採用**。

3. `LCM 実装経路`
- Status: `DECIDED`
- 候補A: SPMF LCMFreq を使用
- 候補B: 公式LCM C実装を直接ラップ
- 推奨: まず `候補A`（ライセンスが明確、比較環境を揃えやすい）。
- 影響: 実行速度と配布ライセンス要件。
- 決定: **推奨どおり候補A（SPMF LCMFreq）を採用**。

## Decision Log

- 2026-03-02: 初期作成。
- 2026-03-02: ユーザー決定を反映。
  - #1 LPFIM support定義: 候補B（件数ベース）
  - #2 PPFPM 実装の正: 候補B（定義式 + 例 + PAMI）
  - #3 LCM 実装経路: 候補A（SPMF LCMFreq）
- 2026-03-02: 実行基盤更新を反映。
  - Stage A ランナーの実行バックエンドは Rust `comparative_mining` に統一。
  - #3 は「仕様上の参照方針」として維持し、SPMF LCMFreq は oracle 比較用途で扱う。
