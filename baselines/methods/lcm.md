# LCM (LCMFreq)

## Fit

- 用途: パターン同定
- 区間検出: 非対応

## I/O

- Input: transaction DB, support threshold
- Output: frequent / closed / maximal itemsets（モード依存）

## Parameters

- `support`
- 列挙モード（frequent/closed/maximal）

## Implementation Notes

- Stage A 比較では frequent に固定する
- 現行ランナーでは Rust `comparative_mining` 経由で実行する
- SPMF LCMFreq は oracle 比較用（仕様確認）として扱う（`DECISIONS.md` #3）

## Risks

- モード不一致で他手法と比較不能になる
- 公式LCM C実装を併用する場合は別途ライセンス確認が必要

## Stage A Role

- パターン同定 reference baseline（高速枠）
