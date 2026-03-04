# PPFPM / GPF-growth

## Fit

- 用途: partial periodic-frequent pattern
- 区間検出: 直接は非対応

## I/O

- Input: temporally ordered transaction DB
- Output: patterns + support + periodic-ratio

## Parameters

- `minSup`, `maxPer`, `minPR`

## Implementation Notes

- 実装は `PAMI` を参照実装（oracle）として採用する（`DECISIONS.md` #2）
- 論文擬似コードより、定義式 + 例 + PAMI 実装を優先する

## Risks

- 論文擬似コード逐語実装は不整合リスクがある

## Stage A Role

- optional reference（主比較には使わない）
