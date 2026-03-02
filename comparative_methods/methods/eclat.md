# Eclat

## Fit

- 用途: パターン同定
- 区間検出: 非対応

## I/O

- Input: transaction DB (vertical/tid-list), `minsup`
- Output: frequent itemsets (+ support)

## Parameters

- `minsup`

## Implementation Notes

- tid-list intersection を DFS で拡張
- timestamp ではなく transaction id を使う

## Risks

- tid-list が大きいとメモリ増

## Stage A Role

- パターン同定 reference baseline
