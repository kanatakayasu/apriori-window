# Paper M: Cybersecurity — Literature Review

## 論文タイトル
サイバー脅威帰属のための密集 ATT&CK 技術共起マイニング

## ターゲット会議
RAID (International Symposium on Research in Attacks, Intrusions and Defenses) / ACSAC (Annual Computer Security Applications Conference)

---

## 1. ATT&CK フレームワークと脅威インテリジェンス

### 1.1 MITRE ATT&CK
- **Strom et al. (2018)** "MITRE ATT&CK: Design and Philosophy" — ATT&CK は攻撃者の戦術・技術・手順 (TTPs) を体系的に記述するナレッジベース。14 の戦術カテゴリ、数百の技術 ID で構成。
- **Al-Shaer et al. (2020)** "Learning the Associations of MITRE ATT&CK Adversarial Techniques" — CTI レポートから ATT&CK 技術の共起を学習。Association Rule Mining を適用し、技術間の依存関係を抽出。
- **Legoy et al. (2020)** "Automated Retrieval of ATT&CK Tactics and Techniques for Cyber Threat Reports" — NLP ベースの自動 ATT&CK マッピング。

### 1.2 攻撃グループのプロファイリング
- **Noor et al. (2019)** "A Machine Learning-based FinTech Cyber Threat Attribution Framework using High-level Indicators of Compromise" — IOC ベースの帰属は回避されやすい。TTP ベースの帰属が推奨される。
- **Perry et al. (2019)** "No Shortcuts: Attribution Through Behavioral Clustering" — 攻撃行動のクラスタリングによる帰属。

## 2. ネットワーク侵入検知データセット

### 2.1 CICIDS 2017/2018
- **Sharafaldin et al. (2018)** "Toward Generating a New Intrusion Detection Dataset and Intrusion Detection Using Machine Learning" — CICIDS 2017: 5日間のトラフィック、Brute Force, DoS, Web Attack, Infiltration, Botnet, PortScan, DDoS を含む。80+ フロー特徴量。
- **CICIDS 2018** — CSE-CIC-IDS2018: AWS 上で生成。10 の攻撃シナリオ。より大規模。

### 2.2 その他のデータセット
- **Moustafa & Slay (2015)** "UNSW-NB15" — 9 攻撃タイプ。49 特徴量。
- **Maciá-Fernández et al. (2018)** "UGR'16" — 実ネットワークトラフィック。4ヶ月分。

## 3. 頻出パターンマイニングとセキュリティ

### 3.1 アラート相関
- **Ning et al. (2004)** "Techniques and Tools for Analyzing Intrusion Alerts" — IDS アラートの相関分析。頻出パターンで攻撃ステップを連結。
- **Sadoddin & Ghorbani (2006)** "Alert Correlation Survey" — アラート相関手法のサーベイ。
- **Ahmadinejad et al. (2009)** "Mining Intrusion Alert Correlations" — Apriori ベースのアラート相関。

### 3.2 攻撃パターン検出
- **Qin & Lee (2004)** "Statistical Causality Analysis of INFOSEC Alert Data" — Granger 因果性でアラートの時間的依存を分析。
- **Julisch (2003)** "Clustering Intrusion Detection Alarms to Support Root Cause Analysis" — アラームクラスタリングで根本原因分析。

### 3.3 時間パターンマイニング
- **Mannila et al. (1997)** "Discovery of Frequent Episodes in Event Sequences" — エピソードマイニング。イベント系列中の頻出パターン発見の先駆的研究。
- **Laxman & Sastry (2006)** "A Survey of Temporal Data Mining" — 時間データマイニングの体系的サーベイ。

## 4. 密集区間マイニング（本研究の基盤）

### 4.1 Apriori-Window
- **本リポジトリの手法** — スライディングウィンドウ × Apriori で密集アイテムセット区間を検出。従来の頻出パターンマイニングが全期間のサポートを計算するのに対し、局所的に密集する区間を明示的に出力。

### 4.2 Rare Dense Patterns (Paper B)
- **Paper B** — 大域的に稀少だが局所的に密集するパターンの検出。Anti-monotone pruning と最小密度閾値の二重フィルタリング。

## 5. キルチェーンと多段階攻撃分析

### 5.1 Cyber Kill Chain
- **Hutchins et al. (2011)** "Intelligence-Driven Computer Network Defense" — ロッキード・マーティンのキルチェーンモデル。Reconnaissance → Weaponization → Delivery → Exploitation → Installation → C2 → Actions。
- **ATT&CK との対応** — ATT&CK の戦術は Kill Chain のフェーズに概ね対応。

### 5.2 多段階攻撃検出
- **Moskal et al. (2020)** "Cyber Threat Assessment for the Air Traffic Management System" — 多段階攻撃のリスク評価。
- **Milajerdi et al. (2019)** "HOLMES: Real-Time APT Detection through Correlation of Suspicious Information Flows" — 情報フロー追跡で APT を検出。

---

## ギャップ分析

### 既存手法の限界

| 手法カテゴリ | 限界 |
|---|---|
| IDS アラート相関 | 単一セッション内。時間的密集性を考慮しない |
| Association Rule Mining on ATT&CK | 全期間の共起頻度のみ。いつ共起が集中したかを出力しない |
| Kill Chain 分析 | 手動マッピング。スケーラブルでない |
| Episode Mining | 順序制約あり。共起の密集区間を直接出力しない |
| 異常検知 (ML) | ブラックボックス。どの技術組合せが密集したか解釈不能 |

### 本研究の差別化ポイント

1. **密集共起区間の明示的検出**: ATT&CK 技術 ID をアイテムとし、時間ビン別ネットワークセグメントをトランザクションとする。密集区間が「いつ」「どの技術組合せ」が集中したかを出力。
2. **キャンペーン推定**: 密集区間の重なりから、同一攻撃キャンペーンに属する技術セットをクラスタリング。
3. **自動帰属**: 密集区間の時間的パターンから、既知の攻撃グループ (APT) の TTP プロファイルとの照合。
4. **Rare Dense 拡張**: Paper B の Rare Dense Pattern を応用し、大域的に稀だが局所的に密集する攻撃パターン（APT 特有の手法）を検出。
