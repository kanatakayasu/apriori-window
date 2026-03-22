# Formalization — Paper M: サイバー脅威帰属のための密集 ATT&CK 技術共起マイニング

## 1. 基本定義

### 定義 1 (ATT&CK 技術アイテム集合)
ATT&CK 技術 ID の有限集合 $\mathcal{T} = \{T_1, T_2, \ldots, T_m\}$ をアイテム集合と定義する。
各 $T_i$ は MITRE ATT&CK の技術 ID (e.g., T1059, T1071) に対応する。

### 定義 2 (セグメント・時間ビントランザクション)
ネットワークセグメント $s \in \mathcal{S}$ と時間ビン $t \in \{1, 2, \ldots, N\}$ の組 $(s, t)$ に対し、
トランザクション $\tau_{s,t} \subseteq \mathcal{T}$ を時間ビン $t$ においてセグメント $s$ で観測された ATT&CK 技術 ID の集合とする。

全トランザクション列: $\mathcal{D} = (\tau_1, \tau_2, \ldots, \tau_N)$
ここで $\tau_t = \bigcup_{s \in \mathcal{S}} \tau_{s,t}$ (全セグメント統合) または
セグメント別にトランザクションを展開する。

### 定義 3 (密集技術共起区間)
技術セット $X \subseteq \mathcal{T}$, ウィンドウサイズ $W$, 密度閾値 $\theta$ に対し、
区間 $[l, r]$ が $X$ の密集区間であるとは:

$$\forall p \in [l, r], \; |\{t \in [p, p+W] : X \subseteq \tau_t\}| \geq \theta$$

### 定義 4 (攻撃キャンペーン)
密集区間の集合 $\mathcal{I} = \{(X_i, [l_i, r_i])\}$ に対し、
時間的重なり度 $\text{overlap}((X_i, [l_i, r_i]), (X_j, [l_j, r_j]))$ を:

$$\text{overlap} = \frac{|[l_i, r_i] \cap [l_j, r_j]|}{|[l_i, r_i] \cup [l_j, r_j]|}$$

重なり度が閾値 $\alpha$ 以上の密集区間の連結成分を攻撃キャンペーンと定義する。

### 定義 5 (脅威グループ TTP プロファイル)
脅威グループ $G$ の TTP プロファイルを $\text{Profile}(G) \subseteq 2^{\mathcal{T}}$ とする。
これは既知の ATT&CK 技術セットの集合。

## 2. 問題定式化

### 問題 1 (密集技術共起区間検出)
**入力**: トランザクション列 $\mathcal{D}$, ウィンドウサイズ $W$, 密度閾値 $\theta$, 最大パターン長 $k_{\max}$
**出力**: $\{(X, \mathcal{I}_X) : X \subseteq \mathcal{T}, |X| \leq k_{\max}, \mathcal{I}_X \neq \emptyset\}$
ここで $\mathcal{I}_X$ は $X$ の密集区間の集合。

### 問題 2 (攻撃キャンペーン推定)
**入力**: 密集区間の集合, 重なり閾値 $\alpha$
**出力**: キャンペーン $\{C_1, C_2, \ldots\}$ (密集区間のクラスタ)

### 問題 3 (脅威グループ帰属)
**入力**: キャンペーン $C_i$, 既知の TTP プロファイル $\{\text{Profile}(G_j)\}$
**出力**: 各キャンペーンに対する帰属スコア $\text{Score}(C_i, G_j)$

## 3. 理論的性質

### 命題 1 (Apriori 性質の保存)
技術セット $X$ が区間 $[l, r]$ で密集区間を持つならば、
$X$ の任意の部分集合 $Y \subset X$ も $[l, r]$ を含む密集区間を持つ。

**証明**: $X \subseteq \tau_t$ ならば $Y \subseteq \tau_t$ であるから、
$X$ の共起カウントは $Y$ の共起カウント以下。
したがって $Y$ のサポートは $X$ のサポート以上であり、密集条件も保存される。 $\square$

### 命題 2 (キャンペーンクラスタリングの計算量)
$n$ 個の密集区間に対し、キャンペーン推定は $O(n^2)$ のペアワイズ重なり計算と
$O(n \cdot \alpha(n))$ の Union-Find で実行可能。ここで $\alpha$ はアッカーマン逆関数。

### 命題 3 (帰属スコアの性質)
Jaccard 類似度に基づく帰属スコア:
$$\text{Score}(C_i, G_j) = \frac{|\text{Techs}(C_i) \cap \text{Profile}(G_j)|}{|\text{Techs}(C_i) \cup \text{Profile}(G_j)|}$$
は $[0, 1]$ の値をとり、$\text{Score} = 1$ のとき完全一致。

## 4. アルゴリズム概要

```
Algorithm: DenseATTACKMiner
Input: トランザクション列 D, W, θ, k_max, α
Output: キャンペーン集合, 帰属結果

1. ATT&CK アダプタでトランザクション変換
2. Apriori-Window で密集技術共起区間を検出
3. 密集区間のペアワイズ重なりを計算
4. Union-Find でキャンペーンをクラスタリング
5. 各キャンペーンの技術セットを集約
6. 既知 TTP プロファイルとの Jaccard 類似度を計算
7. 帰属結果を出力
```
