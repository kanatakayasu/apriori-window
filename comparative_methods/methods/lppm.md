# LPPM (LPPM_depth / LPPM_breadth / LPP-Growth)

## Fit

- 用途: local periodic patterns with periodic intervals
- 区間検出: 対応（主候補）

## I/O

- Input: timestamped transaction DB
- Output: pattern + periodic time-interval(s)

## Parameters

- `maxPer`, `maxSoPer`, `minDur`
- 実装により timestamps 入力フラグ

## Implementation Notes

- ts-list intersection + `time2interval`
- まず `LPPM_depth` を実装対象に固定
- SPMF を oracle にして出力一致テストを行う

## Risks

- 未クローズ区間の閉じ方（tsmax）を落とすと不一致

## Stage A Role

- 区間検出の最優先 reference baseline
