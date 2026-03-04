# FP-Growth

## Fit

- 用途: パターン同定
- 区間検出: 非対応

## I/O

- Input: transaction DB, `minsup`
- Output: frequent patterns (+ support)

## Parameters

- `minsup`

## Implementation Notes

- FP-tree 構築
- conditional pattern base / conditional tree を再帰採掘
- 入力整形（重複禁止、ソート）を Apriori と共通化

## Risks

- 条件木の実装バグで support 不整合が起こりやすい

## Stage A Role

- パターン同定 reference baseline
