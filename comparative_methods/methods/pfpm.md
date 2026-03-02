# PFPM

## Fit

- 用途: 周期頻出パターン抽出
- 区間検出: 直接は非対応

## I/O

- Input: transaction DB, periodicity thresholds
- Output: periodic frequent itemsets + periodicity statistics

## Parameters

- `minPer`, `maxPer`, `minAvg`, `maxAvg`, `minsup`

## Implementation Notes

- Eclat系の vertical 探索
- 出力は区間ではなく periodicity 指標

## Risks

- Stage A の区間検出タスクと直接一致しない

## Stage A Role

- optional reference（周期性フィルタ軸）
