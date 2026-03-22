# Paper H: 密集区間予測 — 記述的から予測的パターンマイニングへ

## ステータス
- **Phase**: 1-6 完了
- **ブランチ**: `paper/H-dense-prediction`
- **ターゲット会議**: KDD / SDM
- **難易度**: 3/5

## 概要

密集区間マイニングの出力を点過程・生存分析の枠組みと接続し、
記述的パターンマイニングから予測的パターンマイニングへの橋渡しを行う。

## 導入概念

1. **Dense Interval Occurrence Process (DIOP)**: 密集区間発生を Hawkes 過程でモデル化
2. **Inter-Dense Interval Time (IDIT)**: 密集区間間の時間間隔の分布分析
3. **Dense Duration Prediction**: Weibull 生存モデルによる持続時間予測

## テスト

```sh
python3 -m pytest paper/H-dense-prediction/implementation/python/tests/ -v
# 26 passed
```

## 実験

```sh
python3 paper/H-dense-prediction/experiments/run_all.py
```

## 論文コンパイル

```sh
cd paper/H-dense-prediction/manuscript && latexmk -pdf main.tex
```
