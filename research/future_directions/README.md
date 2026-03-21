# Apriori-Window 発展方向ブレインストーミング

本ディレクトリは Apriori-Window アルゴリズムの将来的な研究拡張のアイデアを整理する。

## ディレクトリ構成

```
future_directions/
├── README.md                  ← このファイル（全体索引・優先度ランキング）
├── 00_publication_strategy.md ← 論文化戦略（17本+α の計画・引用ネットワーク・ロードマップ）
├── 01_multidimensional.md     ← 多次元密集領域マイニング（時間×空間等）
├── 02_algorithmic.md          ← アルゴリズム拡張（反密集・コントラスト・Top-k等）
├── 03_applications.md         ← 応用ドメイン駆動の拡張
├── 04_ml_integration.md       ← ML/AI との統合
└── 05_fpm_extensions.md       ← 従来FPM拡張パターンからの着想
```

## 優先度ランキング

### Tier 1: 高新規性 × 高実現可能性

| # | アイデア | 新規性 | 難度 | 推奨投稿先 | 詳細 |
|---|---------|--------|------|-----------|------|
| 1 | 多次元密集領域マイニング | Very High | 4/5 | KDD / ICDM | [01](01_multidimensional.md) |
| 2 | 反密集区間 (Anti-Dense) | Very High | 2/5 | DSAA / ICDM | [02](02_algorithmic.md#2-反密集区間-anti-dense-intervals) |
| 3 | コントラスト密集パターン | High | 2/5 | DSAA / ICDM | [02](02_algorithmic.md#3-コントラスト密集パターン) |
| 4 | 稀密集パターン | Very High | 3/5 | KDD / SDM | [05](05_fpm_extensions.md#1-稀密集パターン-rare-dense-patterns) |

### Tier 2: 高新規性 × 中難度

| # | アイデア | 新規性 | 難度 | 推奨投稿先 | 詳細 |
|---|---------|--------|------|-----------|------|
| 5 | 適応的/多スケール窓幅 | High | 4/5 | KDD / VLDB | [02](02_algorithmic.md#1-適応的多スケール窓幅) |
| 6 | 因果帰属への昇格 | Very High | 4/5 | KDD / AAAI | [02](02_algorithmic.md#10-因果帰属) |
| 7 | Top-k 密集パターン | High | 3/5 | ICDM / PAKDD | [02](02_algorithmic.md#4-top-k-密集パターン) |
| 8 | 密集区間予測 | High | 3/5 | KDD / SDM | [02](02_algorithmic.md#5-密集パターン予測) |
| 9 | 高ユーティリティ密集区間 | High | 3/5 | TKDE / KAIS | [05](05_fpm_extensions.md#2-高ユーティリティ密集区間) |
| 10 | MDL 密集区間要約 | High | 4/5 | KDD / ECML | [02](02_algorithmic.md#11-mdl-密集区間要約) |

### Tier 3: 応用ドメイン駆動

| # | ドメイン | データ入手性 | 推奨投稿先 | 詳細 |
|---|---------|------------|-----------|------|
| 11 | 薬剤疫学 | 高 (MIMIC-IV) | JAMIA / AMIA | [03](03_applications.md#1-薬剤疫学) |
| 12 | 製造業故障診断 | 中 | IEEE Trans. SM | [03](03_applications.md#2-製造業故障診断) |
| 13 | サイバーセキュリティ | 中 | USENIX / RAID | [03](03_applications.md#3-サイバーセキュリティ) |
| 14 | 臨床ゲノミクス | 高 | Bioinformatics | [03](03_applications.md#4-臨床ゲノミクス) |
| 15 | ソフトウェアログ | 高 | ICSE / FSE | [03](03_applications.md#5-ソフトウェアログ) |

### Tier 4: ML/AI 統合

| # | アイデア | 推奨投稿先 | 詳細 |
|---|---------|-----------|------|
| 16 | Attention 帰属 | KDD / CIKM | [04](04_ml_integration.md#1-attention-帰属) |
| 17 | 密集パターン特徴量化 | KDD / WWW | [04](04_ml_integration.md#3-密集パターン特徴量化) |
| 18 | LLM パターン解釈 | AAAI / CHI | [04](04_ml_integration.md#4-llm-パターン解釈) |
| 19 | パターン間因果ネットワーク | KDD / AAAI | [04](04_ml_integration.md#11-パターン間因果ネットワーク) |

## 推奨ロードマップ

1. **短期（次の論文）**: #2 反密集区間 or #3 コントラスト密集パターン
2. **中期（半年以内）**: #1 多次元拡張
3. **長期（1年）**: #6 因果帰属への昇格
4. **並行（応用論文）**: #11 薬剤疫学 or #14 ゲノミクス

---

*作成日: 2026-03-21*
*調査方法: 5 並列エージェントによる 200+ 文献サーベイ*
