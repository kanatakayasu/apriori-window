# Dunnhumby — The Complete Journey

## 概要

| 項目 | 内容 |
|------|------|
| 提供元 | dunnhumby （https://www.dunnhumby.com/source-files/） |
| 期間 | 2年（週単位） |
| 主要ファイル | `transaction_data.csv`, `campaign_desc.csv`, `coupon.csv` など |
| 規模 | transaction_data.csv で約 100 万行 |
| ライセンス | dunnhumby の利用規約に従う（要登録・無償） |

## データ取得手順

1. https://www.dunnhumby.com/source-files/ にアクセス
2. 「The Complete Journey」を選択してダウンロード
3. ZIP を解凍し、CSVファイルをこのディレクトリ（`dataset/dunnhumby/`）に配置

```
dataset/dunnhumby/
  transaction_data.csv
  campaign_desc.csv
  campaign_table.csv
  causal_data.csv
  coupon.csv
  coupon_redempt.csv
  hh_demographic.csv
  product.csv
```

## このプロジェクトでの使用用途

- **Stage C** 実験（Phase 1 + Phase 2）
- `transaction_data.csv` の `BASKET_ID` をバスケット、`WEEK_NO` をタイムスタンプとして使用
- `campaign_desc.csv` のキャンペーン期間を外部イベントとして Phase 2 に投入

## 注意

CSV ファイルは `.gitignore` により追跡対象外。
再現実験を行う場合は上記の手順でデータを再取得してください。
