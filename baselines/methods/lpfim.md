# LPFIM

## Fit

- 用途: 区間付き局所頻出パターン
- 区間検出: 対応

## I/O

- Input: timestamped transaction DB
- Output: itemset -> interval list `[start, end]`

## Parameters

- `sigma`, `tau`, `minthd1`, `minthd2`

## Implementation Notes

- Apriori改 + lastseen 更新で interval を管理
- `Lk` を `Ck` から計算する手順は補完実装が必要
- support は **区間内件数ベース** で実装する（`DECISIONS.md` #1）

## Fixed Spec

- support 定義は候補B（件数ベース）を採用済み
- `sigma` は件数閾値として扱う

## Stage A Role

- 区間検出の reference baseline
