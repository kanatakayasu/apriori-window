# 実験設計書（インデックス）

> 対象フェーズ: Phase 3
> 更新: 2026-03-02
> 目的: 実験設計を Stage 単位で分割管理する

---

## ドキュメント構成

- Stage A（合成データ）: `experiments/doc/experiment_design_stage_a.md`
- Stage B（UCI Online Retail II）: `experiments/doc/experiment_design_stage_b.md`

---

## 変更点（2026-03-02）

1. 実験設計を Stage 単位で分割
2. Stage A を「パターン同定」と「区間検出」に明確分離
3. Stage A の比較手法をタスク別に再整理
- パターン同定:
  - 主比較: Phase 1, 従来Apriori-window
  - 参考比較: Apriori, FP-Growth, Eclat, LCM（全体支持度系）
- 区間検出:
  - 主比較: Phase 1, 従来Apriori-window
  - 参考比較: LPFIM, LPPM（区間出力可能手法）

