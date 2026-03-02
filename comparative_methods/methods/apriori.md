# Apriori

## Fit

- 用途: パターン同定
- 区間検出: 非対応

## I/O

- Input: transaction DB, `minsup`
- Output: frequent itemsets (+ support)

## Parameters

- `minsup` (count or ratio; 実装で統一)

## Implementation Notes

- anti-monotonicity による candidate pruning
- transaction 内重複 item 禁止
- item 順序を固定（昇順）

## Risks

- 低 `minsup` で候補爆発

## Stage A Role

- パターン同定の reference baseline（task mismatch）
