# Stage B 実験設計（UCI Online Retail II）

> 対象フェーズ: Phase 3
> 更新: 2026-03-02
> 備考: Stage B は現時点では優先度低。設計記録として分離保持。

---

## 1. 目的

| RQ | 問い |
|----|------|
| **RQ3-B** | 実購買データ（UCI Online Retail II）で Phase 1 適用時に検出パターンはどう変化するか？ |
| **RQ4-B** | 実データ規模で Rust 実装は実用速度か？ |

---

## 2. データ概要

| 項目 | 内容 |
|------|------|
| URL | https://archive.uci.edu/dataset/502/online+retail+ii |
| 期間 | 2009-12〜2011-12 |
| 行数 | 約100万行 |
| 主要列 | InvoiceNo, StockCode, Quantity, InvoiceDate, CustomerID |

---

## 3. 前処理方針

- バスケット = `InvoiceNo`（1回の購買イベント）
- トランザクション = `日付`（同日の全購買を集約）

前処理手順:
1. キャンセル行（`InvoiceNo` が `C` 始まり）除外
2. `Quantity <= 0` 除外
3. `InvoiceDate` から日付抽出
4. 日付ごとにトランザクションID採番
5. `InvoiceNo` ごとにバスケットID採番
6. バスケット構造付き形式へ変換（`item item | item ...`）
7. タイムスタンプはトランザクション連番

---

## 4. 実験計画

### B1: パラメータ感度（Phase 1 のみ）

可変:
- `min_support = 10, 20, 50, 100, 200`
- `window_size = 30, 90, 180`（日）

計測:
- 検出パターン数（`|S|>=2`）
- 密集区間数
- 実行時間（Rust）

### B2: 従来法 vs Phase 1

固定:
- `min_support=50, window_size=90`

比較:
- 従来法が追加検出するパターン数
- 代表パターンの定性確認（偽共起候補）

### B3: スケーラビリティ

期間切り取りで規模を変更:
- 1ヶ月 / 6ヶ月 / 12ヶ月 / 全期間

計測:
- 実行時間
- メモリ

---

## 5. ファイル構成

```
dataset/
  uci_retail/
    preprocess_uci.py
    online_retail_II.xlsx
    output/
      uci_basket.txt
      uci_basket_metadata.json
    settings/
    results/
```

