# Related Work Survey — 密集区間とイベントの時間的関係抽出パイプライン

> **作成日**: 2026-03-17
> **対象**: Phase 2 — 4段パイプライン（MI 事前フィルタ + Sweep Line + 置換検定）の関連研究・先行研究・類似研究

---

## 目次

1. [Allen の区間代数とデータマイニング](#1-allen-の区間代数とデータマイニング)
2. [時間的アソシエーションルールマイニング](#2-時間的アソシエーションルールマイニング)
3. [スライディングウィンドウ上の密集区間・バースト検出](#3-スライディングウィンドウ上の密集区間バースト検出)
4. [イベント相関・トランザクション間関係](#4-イベント相関トランザクション間関係)
5. [MI による時系列ペアの事前フィルタリング（Stage 1 関連）](#5-mi-による時系列ペアの事前フィルタリングstage-1-関連)
6. [Sweep Line / Interval Join アルゴリズム（Stage 2 関連）](#6-sweep-line--interval-join-アルゴリズムstage-2-関連)
7. [統計的有意性検定・置換検定（Stage 3 関連）](#7-統計的有意性検定置換検定stage-3-関連)
8. [多重検定補正](#8-多重検定補正)
9. [時間的共起の有意性検定](#9-時間的共起の有意性検定)
10. [本パイプラインの位置づけと新規性](#10-本パイプラインの位置づけと新規性)

---

## 1. Allen の区間代数とデータマイニング

### 1.1 基礎理論

| 論文 | 会場 | 概要 |
|------|------|------|
| **Allen, J.F.** "Maintaining Knowledge about Temporal Intervals" | *Communications of the ACM*, 1983 | 2 つの時間区間間の 13 種の基本関係（before, after, meets, overlaps, during, starts, finishes 等）を定義。時間推論の合成表を提供し、時間的知識表現の基盤を確立。**本パイプラインの 6 種時間的関係（DFE/EFD/DCE/ECD/DOE/EOD）は Allen 13 関係のサブセットに相当する。** |

### 1.2 区間パターンマイニング（TIRP）

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Moskovitch & Shahar**, "Fast Time Intervals Mining Using the Transitivity of Temporal Relations" (KarmaLego) | *Knowledge and Information Systems*, 2015 | Allen 関係を利用して Time-Interval Related Pattern (TIRP) を高速発見。推移律による候補削減。 | 密集区間を「シンボリック時間区間」と見なせば、外部イベントとの関係発見は TIRP マイニングの一種。ただし KarmaLego は既知区間間の関係パターン頻度計算が主目的。 |
| **Moskovitch & Shahar**, "Classification of Multivariate Time Series via Temporal Abstraction and Time Intervals Mining" (KLS) | *Knowledge and Information Systems*, 2015 | (1) 時系列をシンボリック時間区間に変換、(2) Allen 関係で TIRP をマイニング、(3) 分類器構築。 | Phase 1（密集区間抽出）+ Phase 2（外部イベント相関）の流れと、KLS の「時間抽象化→パターン発見→下流タスク」に構造的類似性。 |
| **Kam & Fu**, "Discovering Temporal Patterns for Interval-Based Events" | *DaWaK*, 2000 | 区間ベースイベントからの時間パターン発見の初期研究。 | 密集区間が区間ベースイベントの一種として位置づけられる。 |
| **Papapetrou et al.**, "Mining Nonambiguous Temporal Patterns" (TPMiner) | *IEEE TKDE*, 2009 | IEMiner の 6 倍高速な TPMiner。ε-relaxed Allen 関係による TIRP 定義の基礎。 | 密集区間と外部イベント区間のペアからパターン発見する効率的アルゴリズムの参考。 |
| **Hirsch et al.**, "TIRPClo" | *DMKD*, 2023 / *AAAI*, 2021 | 閉パターンによる完全な TIRP マイニング。 | 出力の冗長性削減の参考。 |
| **"TIRPMiner"** | *Information Sciences*, 2025 | 位置圧縮アルゴリズムと枝刈り戦略 (UCTP/UCOP)。 | 大規模データへのスケーリング手法。 |

---

## 2. 時間的アソシエーションルールマイニング

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Agrawal & Srikant**, "Mining Sequential Patterns: Generalizations and Performance Improvements" | *EDBT*, 1996 | minimum gap, maximum gap, sliding time-window の 3 種時間制約を導入。 | スライディングウィンドウによるパターン発見の直接的先行研究。ただし逐次パターン（順序あり）が対象。 |
| **Özden, Ramaswamy & Silberschatz**, "Cyclic Association Rules" | *ICDE*, 1998 | 時間的に周期的変動を示すアソシエーションルールの発見。cycle pruning による効率化。 | 密集区間の周期性分析の理論的背景。 |
| **Ale & Rossi**, "An Approach to Discovering Temporal Association Rules" | *ACM SAC*, 2000 | アイテムの lifespan に基づく時間的サポート定義。データ内在的に時間的ルールを発見。 | 密集区間の開始・終了がデータ駆動で決まる点で思想が近い。 |
| **Giannotti, Nanni & Pedreschi**, "Efficient Mining of Temporally Annotated Sequences" | *SDM*, 2006 | パターン要素間の時間間隔情報を保持する時間注釈付き逐次パターン。 | 密集区間-外部イベント間の時間的距離を注釈として保持する拡張の理論的基盤。 |
| **Segura-Delgado et al.**, "Temporal Association Rule Mining: An Overview" | *WIREs DMKD*, 2020 | 時間変数の分類法によるサーベイ。 | 本パイプラインの位置づけを俯瞰的に整理するための包括的参考文献。 |

---

## 3. スライディングウィンドウ上の密集区間・バースト検出

### 3.1 ストリームマイニング

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Mannila, Toivonen & Verkamo**, "Discovery of Frequent Episodes in Event Sequences" | *DMKD*, 1997 | スライディングウィンドウ上で頻出エピソードを発見する基盤アルゴリズム。 | Apriori-window のウィンドウ上局所パターン発見の直接的な理論的祖先。 |
| **Chang & Lee**, "Sliding Window-based Frequent Pattern Mining over Data Streams" | *Information Sciences*, 2009 | ウィンドウ移動に伴うパターンの追加・削除を差分的に処理。 | ウィンドウスライド時の差分更新効率化の参考。 |
| **Li et al.**, "Mining Frequent Itemsets Using the Weighted Sliding Window Model" | *Expert Systems with Applications*, 2009 | 重み付きスライディングウィンドウで最近データを重視。 | 密集区間内での時間重み付けサポート計算の参考。 |
| **Jiang & Gruenwald**, "Efficient Frequent Itemset Mining Methods over Time-Sensitive Streams" | *Knowledge-Based Systems*, 2013 | トランザクション到着率の時間変動を考慮。 | 実データ（ピーク時間帯等）への適用で重要。 |

### 3.2 バースト検出

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Kleinberg**, "Bursty and Hierarchical Structure in Streams" | *KDD*, 2002 | 確率的オートマトンに基づくバースト検出。低頻度/高頻度状態の遷移としてバーストを定式化。 | Phase 1（密集区間検出）と強い類似性。Kleinberg はイベント列のバースト区間を検出するが、アイテムセットのバーストではない。Apriori-window は「パターン特化型バースト検出」と見なせる。 |
| **Li et al.**, "Multi-type Concept Drift Detection under a Dual-Layer Variable Sliding Window" | *Journal of Cloud Computing*, 2023 | 可変スライディングウィンドウで概念ドリフト（突発的・漸進的・段階的）を検出。 | 密集区間の出現・消失を概念ドリフトと見なす視点。 |

---

## 4. イベント相関・トランザクション間関係

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Tung, Lu, Han & Feng**, "Efficient Mining of Intertransaction Association Rules" (FITI) | *IEEE TKDE*, 2003 | トランザクション内頻出アイテムセットを基にトランザクション間アソシエーションを構築。 | Phase 2 の「密集区間（パターン由来）と外部イベント（別系列）の時間的相関」は広義のトランザクション間アソシエーション変形。 |
| **Fournier-Viger et al.**, "Mining Local Periodic Patterns" (LPPM/LPP-Growth) | *Information Sciences*, 2020 | maxSoPer と minDur で局所的周期パターンを自動検出。 | Apriori-window に最も近い先行研究の一つ。ただし LPPM は「周期性」で区間定義、本研究は「ウィンドウ内サポート閾値」で密集定義する根本的差異。 |
| **Guidotti et al.**, "Personalized Market Basket Prediction with TARS" | 2020 | 共起性・逐次性・周期性・再帰性を同時に捕捉する TARS パターン。 | 購買パターンの時間的側面を明示的にモデル化する応用先の参考。 |

---

## 5. MI による時系列ペアの事前フィルタリング（Stage 1 関連）

### 5.1 コア論文群

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Ho, Ho & Pedersen**, "Efficient Temporal Pattern Mining in Big Time Series Using Mutual Information" (FTPMfTS) | *VLDB*, 2022 | IoT 大規模時系列から MI を用いて時間区間付きパターン候補を高速スクリーニング。MI の上界/下界による枝刈り。 | **Stage 1 の直接的先行研究。** MI による候補ペアスクリーニングアーキテクチャの理論的根拠を提供。 |
| **Ho, Ho, Pedersen & Papapetrou**, (拡張版) | *IEEE TKDE*, 2025 (arXiv: 2306.10994) | FTPMfTS の一般化。頻出パターンだけでなく稀少パターンにも MI フィルタを拡張。 | MI フィルタの適用範囲が低頻度密集区間にも有効であることの根拠。 |
| **Ho, Pedersen, Ho, Vu & Biscio**, "Efficient Bottom-Up Discovery of Multi-scale Time Series Correlations Using MI" | *IEEE ICDE*, 2019 | 多スケール時系列相関の MI ベースボトムアップ発見。 | 異なる時間スケールの密集区間に対する多スケール MI スクリーニング。 |

### 5.2 関連手法

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Pan et al.**, "NLC: Search Correlated Window Pairs on Long Time Series" | *VLDB*, 2022 | 異なる遅延・長さの相関ウィンドウペアを効率探索。 | 密集区間と外部イベントの「相関ウィンドウペア」探索と問題構造が非常に類似。 |
| **Zhu & Shasha**, "StatStream: Statistical Monitoring of Thousands of Data Streams in Real Time" | *VLDB*, 2002 | DFT ベーススケッチでスライディングウィンドウ上の Pearson 相関ペアをリアルタイム発見。 | MI の代わりに Pearson 相関を用いたストリーミング事前フィルタリングの先駆的研究。 |
| **Chen & Shrivastava**, "Efficiently Estimating MI Between Attributes Across Tables" (TUPSK) | *IEEE ICDE*, 2024 (arXiv: 2403.15553) | Join を実体化せずにテーブル間属性の MI を推定するスケッチ手法。 | 密集区間テーブルと外部イベントテーブルの Temporal Join 前の MI スクリーニングコスト回避。 |

---

## 6. Sweep Line / Interval Join アルゴリズム（Stage 2 関連）

### 6.1 コア論文群

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Bouros & Mamoulis**, "A Forward Scan based Plane Sweep Algorithm for Parallel Interval Joins" | *VLDB*, 2017 | 開始端点ソート + Forward Scan ベース Plane Sweep で並列 Interval Join。 | **Stage 2 の直接的ベースアルゴリズム。** Forward Scan の方向が Apriori Window の時間順探索と整合。 |
| **Christodoulou, Bouros & Mamoulis**, "HINT: A Hierarchical Index for Intervals in Main Memory" | *SIGMOD*, 2022 / *VLDB Journal*, 2024 | 階層的区間分割インメモリインデックス。Allen 13 関係すべてに対応。既存手法の 1 桁以上の高速化。 | 6 種時間的関係 (DFE/EFD/DCE/ECD/DOE/EOD) のクエリを統一的かつ高速に処理可能。GitHub: [pbour/hint](https://github.com/pbour/hint) |
| **Piatov, Helmer, Dignos & Persia**, "Cache-efficient Sweeping-based Interval Joins for Extended Allen Relation Predicates" | *VLDB Journal*, 2021 | パラメタ付き Allen 関係に対応するキャッシュ効率的 Sweep アルゴリズム。Gapless Hash Map による最適化。 | ε-tolerant な時間的関係を実装する際のアルゴリズム基盤。パラメタ付き Allen 関係は本研究の 6 種の一般化に相当。 |

### 6.2 関連手法

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Kaufmann et al.**, "Timeline Index: A Unified Data Structure for Processing Queries on Temporal Data in SAP HANA" | *SIGMOD*, 2013 | 時間的集約・タイムトラベル・時間的結合を統一サポート。 | 密集区間の集約と外部イベントとの結合を単一データ構造で処理する設計指針。 |
| **Dignos, Bohlen, Gamper, Jensen & Moser**, "Leveraging Range Joins for the Computation of Overlap Joins" | *VLDB Journal*, 2022 | Overlap Join を Range Join の合併として定式化。B+-Tree で効率実行。 | Apriori Window 出力区間と外部イベント区間の overlap 判定を Range Join に変換する戦略の根拠。 |
| **Hu, Sintos, Gao, Agarwal & Yang**, "Computing Complex Temporal Join Queries Efficiently" | *SIGMOD*, 2022 | 多方向時間的結合を worst-case optimal に処理。 | 複数外部イベント系列との同時マッチング（多対多の時間的結合）でペアワイズ処理の爆発を回避。 |

---

## 7. 統計的有意性検定・置換検定（Stage 3 関連）

### 7.1 置換検定ベースの有意パターンマイニング

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Llinares-Lopez, Sugiyama, Papaxanthos & Borgwardt**, "Westfall-Young Light" (WY-light) | *KDD*, 2015 | WY 置換手続きで FWER を厳密制御。再マイニング不要の枝刈りで実行時間・メモリを劇的削減。 | **Stage 3 の直接的先行研究。** パターン間の相関を考慮した FWER 制御。密集区間-イベント対の有意性評価に直接応用可能。 |
| **Pellegrina & Vandin**, "Efficient Mining of the Most Significant Patterns with Permutation Testing" | *DMKD*, 2020 | Tarone の検定可能性基準と WY 置換を組合せ、統計的検出力を最大化。 | パターン-イベント対が膨大な場合の効率的有意性評価。 |
| **Pellegrina & Vandin**, "FSR: Few-Shot Resampling" | *VLDB*, 2024 (arXiv: 2406.11803) | 少数リサンプルのみでパターンの統計的有意性を保証。 | 密集区間マイニングの計算コストが高い場合の高速有意性判定。 |

### 7.2 偽発見制御付きパターンマイニング

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Webb**, "Discovering Significant Patterns" | *Machine Learning*, 2007 | 直接補正法とホールドアウト法の比較。ホールドアウト法のバイアスを指摘。 | 探索-検証の二段階評価の設計指針。 |
| **Gionis, Mannila, Mielikainen & Tsaparas**, "Swap Randomization" | *ACM TKDD*, 2007 | 行・列マージン保存ランダムデータでマイニング結果の有意性をマクロ評価。 | マイニング結果全体の有意性評価アプローチ。 |
| **SPuManTE** (Pellegrina, Riondato & Vandin) | *KDD*, 2019 | 非条件付き検定 (UT) 導入。VC 次元理論で効率的 FWER 制御。 | Fisher 検定の条件付き仮定が不適切な場合の代替手段。 |
| **SPASS** (Dalleiger & Vreeken) | *KDD*, 2022 | 逐次的偽発見制御で冗長パターン排除。 | 重複・冗長なパターン-イベント対の絞り込み。 |
| **FASM / FAST-YB** | *ICDM*, 2023 | BH/BY 手続きベースの FDR 制御。パターン間依存性考慮。 | FWER より緩い FDR 制御で十分な探索的解析段階に有効。 |
| **SPEck** (Jenkins, Walzer-Goldfeld & Riondato) | *DMKD*, 2022 | 系列パターン有意性マイニングの汎用フレームワーク。厳密サンプリング。 | 時間的順序を保存するヌルモデル設計の参考。 |

---

## 8. 多重検定補正

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Terada, Okada-Hatakeyama, Tsuda & Sese**, "LAMP: Limitless Arity Multiple-testing Procedure" | *PNAS*, 2013 | Tarone の検定可能性に基づき検定不可能パターンを除外、Bonferroni 補正の分母を最小化。 | 区間数 × イベント種 × 関係種の膨大な組合せでの Bonferroni 保守性を緩和。 |
| **Minato, Uno & Borgwardt**, "Significant Subgraph Mining with Multiple Testing Correction" | *SDM*, 2015 | Tarone の改良 Bonferroni 補正をグラフマイニングに適用。 | 離散検定でパターン-イベント共起を評価する場合に Tarone 補正が直接適用可能。 |
| **Webb**, "Layered Critical Values" | *Machine Learning*, 2008 | 探索空間の領域別に異なる臨界値を階層化。 | 6 種時間的関係ごとに異なる臨界値設定が可能。 |

---

## 9. 時間的共起の有意性検定

| 論文 | 会場 | 概要 | 本研究との関連 |
|------|------|------|---------------|
| **Haiminen, Mannila & Terzi**, "Determining significance of pairwise co-occurrences of events in bursty sequences" | *BMC Bioinformatics*, 2008 | バースト系列（ゲノム上の結合部位等）のペアワイズ共起有意性評価。バースト構造保存ヌルモデル構築。 | **本研究に最も直接的に関連する先行研究の一つ。** 密集区間（バースト区間）と外部イベントの時間的近接が偶然かどうかの検定で、バースト構造保存ヌルモデルが必須。 |
| **Liang & Sander**, "Detecting Statistically Significant Temporal Associations" (MAM) | *Canadian AI*, 2013 | 複数イベント系列の同期・非同期時間的関連を二段階で検出。時間的ラグ考慮。 | 6 種時間的関係の有意性検定（DFE: 密集先行, EFD: イベント先行 等のラグ考慮）の参考。 |

### 9.1 シャッフル戦略の先行研究

| 手法 | 起源 | 特徴 | 本研究との関連 |
|------|------|------|---------------|
| **円形シフト (Circular Shift)** | Amarasingham et al., 2012（神経科学） | 各系列の自己相関構造（バースト性）保存、系列間共分散を破壊。 | 推奨戦略。密集区間系列と外部イベント系列の両方のバースト構造を保存したまま時間的関連の有意性を検定。 |
| **ブロックブートストラップ** | Kunsch, 1989 (Moving Block Bootstrap) | ブロック単位リサンプリングでブロック内自己相関を保存。 | 非定常な密集区間出現パターン（季節性等）の場合に有効。ブロック長選択に注意。 |
| **サロゲートデータ法** | Theiler et al., 1992 | 保存すべき性質を明示的に選択してサロゲート生成。最も柔軟。 | 密集区間-イベント間の有意性検定の最も一般的フレームワーク。 |

---

## 10. 本パイプラインの位置づけと新規性

### 10.1 構成要素と先行研究の対応

| パイプライン構成要素 | 最も関連の深い先行研究 |
|---------------------|----------------------|
| Phase 1: スライディングウィンドウ上の局所サポート評価 | Mannila+ (1997), Kleinberg (2002), Chang & Lee (2009) |
| Phase 1: 密集区間の厳密抽出 | LPPM (Fournier-Viger+ 2020), LPFIM (Mahanta+ 2005) |
| Stage 1: MI 事前フィルタ | Ho+ (VLDB 2022), Pan+ (VLDB 2022) |
| Stage 2: Sweep Line マッチング | Bouros & Mamoulis (VLDB 2017), HINT (SIGMOD 2022) |
| Stage 3: 置換検定 + 多重検定補正 | WY-light (KDD 2015), Haiminen+ (2008) |
| 全体: パターン→区間→イベント相関 | KLS (Moskovitch & Shahar 2015) が最も構造的に類似 |

### 10.2 先行研究に見られない組合せ

1. **MI 事前フィルタ + Sweep Line Interval Join の統合**: Ho et al. (2022) は MI を temporal pattern mining 内部で使用し、Bouros & Mamoulis (2017) は汎用 Interval Join を扱うが、両者の明示的組合せは先行研究に見られない。
2. **密集区間の時間的共起の情報理論的定量化**: 密集アイテムセット区間を二値時系列に変換し MI で外部イベントとの関連を定量化する枠組みは新規。
3. **偽共起排除（Phase 1）+ 偽時間的関係排除（Phase 2）の二重フレームワーク**: Phase 1 でパターンレベルの偽陽性を排除し、Phase 2 で関係レベルの偽陽性を排除する一貫したストーリーは独自。

### 10.3 推奨引用リスト

パイプライン設計文書 (`doc/temporal_relation_pipeline.md`) で言及済みの論文に加え、以下を論文で引用すべき候補とする。

| 論文 | 引用理由 |
|------|---------|
| Moskovitch & Shahar (2015) KarmaLego | Allen 関係ベース区間パターンマイニングの代表的手法 |
| Mannila+ (1997) 頻出エピソード | スライディングウィンドウ上パターン発見の基盤 |
| Kleinberg (2002) バースト検出 | 密集区間検出との対比 |
| Haiminen+ (2008) バースト系列共起検定 | Stage 3 のヌルモデル設計の直接的先行研究 |
| Pellegrina & Vandin (2020) | 置換検定 + 枝刈りの統合 |
| LAMP / Terada+ (2013) | 多重検定補正の効率化 |
| Segura-Delgado+ (2020) サーベイ | 時間的アソシエーションルール分野の俯瞰 |
| Piatov+ (2021) | ε-tolerant Allen 関係の Sweep Join |

---

## 参考文献一覧

### Allen 区間代数・TIRP
- Allen, J.F. (1983). Maintaining Knowledge about Temporal Intervals. *Commun. ACM*, 26(11), 832-843.
- Moskovitch, R. & Shahar, Y. (2015). Fast Time Intervals Mining Using the Transitivity of Temporal Relations. *KAIS*, 42(1), 21-48.
- Moskovitch, R. & Shahar, Y. (2015). Classification of Multivariate Time Series via Temporal Abstraction and Time Intervals Mining. *KAIS*, 45(1), 35-74.
- Kam, P.S. & Fu, A.W.C. (2000). Discovering Temporal Patterns for Interval-Based Events. *DaWaK*.
- Papapetrou, P. et al. (2009). Mining Nonambiguous Temporal Patterns. *IEEE TKDE*, 21(10).
- Hirsch, T. et al. (2023). TIRPClo: Mining Complete and Closed Time Interval-Related Patterns. *DMKD*.

### 時間的アソシエーションルール
- Agrawal, R. & Srikant, R. (1996). Mining Sequential Patterns: Generalizations and Performance Improvements. *EDBT*.
- Özden, B. et al. (1998). Cyclic Association Rules. *ICDE*.
- Ale, J.M. & Rossi, G.H. (2000). An Approach to Discovering Temporal Association Rules. *ACM SAC*.
- Giannotti, F. et al. (2006). Efficient Mining of Temporally Annotated Sequences. *SDM*.
- Segura-Delgado, A. et al. (2020). Temporal Association Rule Mining: An Overview. *WIREs DMKD*.

### スライディングウィンドウ・バースト
- Mannila, H. et al. (1997). Discovery of Frequent Episodes in Event Sequences. *DMKD*, 1(3), 259-289.
- Kleinberg, J. (2002). Bursty and Hierarchical Structure in Streams. *KDD*.
- Chang, J.H. & Lee, W.S. (2009). Sliding Window-based Frequent Pattern Mining over Data Streams. *Information Sciences*.
- Li, H.F. et al. (2009). Mining Frequent Itemsets Using the Weighted Sliding Window Model. *Expert Systems with Applications*.

### MI フィルタリング
- Ho, V.L. et al. (2022). Efficient Temporal Pattern Mining in Big Time Series Using Mutual Information. *PVLDB*, 15(3), 673-685.
- Ho, V.L. et al. (2025). Generalized Temporal Pattern Mining via MI. *IEEE TKDE*. (arXiv: 2306.10994)
- Ho, N. et al. (2019). Efficient Bottom-Up Discovery of Multi-scale Time Series Correlations Using MI. *ICDE*.
- Pan, S. et al. (2022). NLC: Search Correlated Window Pairs on Long Time Series. *PVLDB*, 15(7).
- Zhu, Y. & Shasha, D. (2002). StatStream. *VLDB*.

### Interval Join
- Bouros, P. & Mamoulis, N. (2017). A Forward Scan based Plane Sweep Algorithm for Parallel Interval Joins. *PVLDB*, 10(11), 1346-1357.
- Christodoulou, G. et al. (2022). HINT: A Hierarchical Index for Intervals in Main Memory. *SIGMOD*.
- Christodoulou, G. et al. (2024). HINT: A Hierarchical Interval Index for Allen Relationships. *VLDB Journal*, 33(1), 73-100.
- Piatov, D. et al. (2021). Cache-efficient Sweeping-based Interval Joins. *VLDB Journal*, 30, 203-226.
- Dignos, A. et al. (2022). Leveraging Range Joins for the Computation of Overlap Joins. *VLDB Journal*, 31, 75-99.
- Hu, X. et al. (2022). Computing Complex Temporal Join Queries Efficiently. *SIGMOD*.

### 統計的有意性検定
- Llinares-Lopez, F. et al. (2015). Fast and Memory-Efficient Significant Pattern Mining via Permutation Testing. *KDD*.
- Pellegrina, L. & Vandin, F. (2020). Efficient Mining of the Most Significant Patterns with Permutation Testing. *DMKD*.
- Pellegrina, L. & Vandin, F. (2024). FSR: Few-Shot Resampling. *PVLDB*. (arXiv: 2406.11803)
- Terada, A. et al. (2013). LAMP. *PNAS*, 110(32), 12996-13001.
- Pellegrina, L. et al. (2019). SPuManTE. *KDD*.
- Dalleiger, S. & Vreeken, J. (2022). SPASS. *KDD*.
- Webb, G.I. (2007). Discovering Significant Patterns. *Machine Learning*, 68(1), 1-33.
- Gionis, A. et al. (2007). Swap Randomization. *ACM TKDD*, 1(3).

### 時間的共起の有意性
- Haiminen, N. et al. (2008). Determining significance of pairwise co-occurrences in bursty sequences. *BMC Bioinformatics*, 9:336.
- Liang, Z. & Sander, J. (2013). Detecting Statistically Significant Temporal Associations. *Canadian AI* (LNCS 7884).

### イベント相関
- Tung, A.K.H. et al. (2003). Efficient Mining of Intertransaction Association Rules. *IEEE TKDE*.
- Fournier-Viger, P. et al. (2020). Mining Local Periodic Patterns. *Information Sciences*.
- Guidotti, R. et al. (2020). Personalized Market Basket Prediction with TARS.
