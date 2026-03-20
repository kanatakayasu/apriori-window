# Event Attribution Pipeline — 実験設計書

## 実験一覧

| 実験 | 目的 | データ | 実行スクリプト |
|------|------|--------|---------------|
| E1a | Clean signal 検出能力 | 合成 (boost=8, N=5K) | `run_e1.py` |
| E1b | Boost 感度 | 合成 (boost 2-15) | `run_e1.py` |
| E1c | イベント重複時の挙動 | 合成 (重複イベント) | `run_e1.py` |
| E1d | 植え込み数×デコイ数 | 合成 (可変) | `run_e1.py` |
| E2 | パラメータ感度分析 | 合成 (固定) | `run_e2.py` |
| E3 | スケーラビリティ | 合成 (N 1K-20K) | `run_e3.py` |
| E4 | 実データ検証 | T10I4D100K, retail | `run_e4.py` |

## 合成データ設計

植え込みパターンは語彙外アイテム (ID 1001+) を使用。ベース語彙 (1-200) の
アイテムとの共起が発生しないため、評価時の FP/TP 判定が明確になる。

## 評価指標

- Precision, Recall, F1（厳密一致: パターン×イベントIDの完全一致）
- 実行時間の内訳（Phase1 / Support Series / Attribution）
