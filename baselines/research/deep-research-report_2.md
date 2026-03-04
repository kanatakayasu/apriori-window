# LPFIM（Mahanta 2005）とPPFPM/GPF-growth（Kiran 2017 JSS）の一次情報ベース仕様調査

## エグゼクティブサマリー

LPFIM（Mahantaら, 2005）は、**時刻付きトランザクションDB**（時間順に整列）を入力として、各アイテムセットについて「局所的に頻出となる時間区間」の**リスト（[start,end]）**を出力する枠組みを提示しています。区間は明示的に**閉区間 [t1,t2]（端点含む）**として定義され、局所supportは区間内の出現率（比率）として定義されています。citeturn13view0turn13view1 一方で、「頻出判定式」の表記に**比率と件数が混在して見える箇所**があり、実装時に解釈を確定する必要があります（後述の「未確定事項」）。citeturn13view0turn13view1 なお、原論文は「実装中」と述べるのみで、著者の公式配布コードURLは提示されていません。citeturn16view1

PPFPM/GPF-growth（Kiranら, JSS 2017）は、**時系列順のトランザクションDB**から、頻度（support）と周期性（periodic-ratio）を同時に満たす**partial periodic-frequent patterns**を列挙します。supportは**件数**、periodは**先頭端（tsini=0）と末尾端（tsfin）を含む差分列**として数学的に定義され、periodic-ratioは「maxPer以内のperiodの割合」として厳密に定義されています。citeturn21view0turn25view0 また本論文はアルゴリズム（Algorithm 1〜6）を掲載していますが、いくつかの擬似コード行に**不整合（符号・不等号・条件分岐）**が疑われ、再現実装では**定義式＋例（Example 5等）**を優先して仕様を確定するのが安全です。citeturn23view3turn22view1turn25view0 著者関係の一次実装としては、後年公開のPythonライブラリ **PAMI** にGPF-growth実装（GPLv3）が含まれ、論文DOI参照も明記されています。citeturn17view0turn10view1turn10view2

## LPFIM（Mahanta et al., 2005: “Finding Locally and Periodically Frequent Sets and Periodic Association Rules”）

### 確定事項

**一次情報（必須URL）**  
- 原論文PDF: `https://link.springer.com/content/pdf/10.1007/11590316_91.pdf` citeturn4view0  
- DOI（章情報）: `https://doi.org/10.1007/11590316_91`（Springer章ページ内に記載） citeturn3view0turn4view0  

**公式/著者実装**  
- 原論文では「実装中」と述べるのみで、配布コードURLは提示されません。よって一次情報ベースでは **未公開** 扱いが妥当です。citeturn16view1  

**入力形式（問題設定の入力）**  
- 入力DBは、各トランザクションが **(アイテム集合, タイムスタンプ)** を持つ時刻付きトランザクションDBで、**タイムスタンプ昇順に整列されている**と仮定されています。citeturn13view0turn19view1  
- タイムスタンプは線形順序が定義できる列 `T=<t0,t1,...>` として置かれており、数値・日時の別などのデータ型は固定されていません（ただし後段で「calendar dates」も言及）。citeturn19view1turn19view0  

**区間の表現（出力の核）**  
- 時間区間は **閉区間 [t1,t2]** と明記され、区間内判定は `t1 ≤ t ≤ t2`（端点含む）です。citeturn13view0  
- 各「locally frequent itemset」には、そのitemsetが頻出となる **時間区間リスト**を保持し、各区間は **[start, end]** で表現されます。区間長は `end - start` と定義されています。citeturn13view0  
- 非重複区間 [start1,end1], [start2,end2] で start2 > end1 のとき、区間間距離を `start2 - end1` と定義しています。citeturn13view0  

**support / confidence の定義（厳密定義式）**  
- 局所supportは「区間内でXを含むトランザクション数 / 区間内総トランザクション数」として定義されています（比率）。citeturn13view0turn19view1  
  - 数式（論文記述の再表現）  
    - 区間内トランザクション集合：  
      \[
      D_{[t_1,t_2]}=\{ \text{trans } r \in D \mid t_1 \le ts(r) \le t_2 \}
      \]
    - 局所support：  
      \[
      Sup_{[t_1,t_2]}(X)=\frac{|\{r\in D_{[t_1,t_2]} \mid X\subseteq items(r)\}|}{|D_{[t_1,t_2]}|}
      \]
    端点を含むのは `t1 ≤ t ≤ t2` の定義に従います。citeturn13view0  
- ルールの時間区間内confidenceは  
  \[
  \frac{Sup_{[t_1,t_2]}(X\cup Y)}{Sup_{[t_1,t_2]}(X)} \ge \tau/100
  \]
  かつ `X∪Y` が区間内で頻出、という形で定義されています。citeturn13view0  

**パラメータ（論文中で意味が確定しているもの）**  
- `minthd1`: 直前出現からの時間ギャップがこれ未満なら**同一局所区間に継続**、そうでなければ**新しい区間開始**。citeturn13view1turn19view1  
- `minthd2`: 区間長（`end-start` 相当）がこれ以上の区間のみ保持（短すぎる区間は捨てる）。citeturn13view1turn13view2  
- `σ`: 最小support閾値（百分率で扱っている実装記述がある）。citeturn13view1turn13view0  
- `τ`: 最小confidence閾値（%表現）。citeturn13view0  

**擬似コード/実装手順（再現に必要な粒度）**  
原論文は、(i) 1-itemsetの局所区間抽出（Algorithm 4.1）と、(ii) Apriori生成＋区間リスト交差による枝刈り（Algorithm 4.2/Prune手順）を提示します。citeturn13view1turn13view2  
再現実装に必要な粒度で、論文アルゴリズムを「手順」として整理すると以下です（**論文のAlgorithm 4.1/4.2/Pruneに基づく再記述**）。citeturn13view1turn13view2  

- 手順（L1生成：Algorithm 4.1相当）citeturn13view1  
  1. 全アイテム `ik (k=1..n)` について、区間リスト `tp[k]` を空で初期化。  
  2. 各アイテムに対し `lastseen[k]=0`, `firstseen[k]=0`, `itemcount[k]=0`, `transcount[k]=0` を初期化。citeturn13view1  
  3. DBを時間順に1パスし、各トランザクション（時刻 `tm`）について、各アイテム `ik` を更新：citeturn13view1  
     - もし `ik` がトランザクションに含まれる：  
       - 初出（lastseen=0）なら `firstseen=lastseen=tm`, `itemcount=transcount=1`。citeturn13view1  
       - そうでなく、`tm - lastseen < minthd1` なら同一区間継続として `lastseen=tm`, `itemcount++`, `transcount++`。citeturn13view1  
       - それ以外（ギャップが閾値以上）なら、直前区間 `[firstseen,lastseen]` を「長さとsupportが閾値を満たすなら」`tp[k]` に追加し、区間を `tm` から再開始（`firstseen=lastseen=tm`, `itemcount=transcount=1`）。citeturn13view1turn19view1  
     - もし `ik` が含まれない：`transcount++`（区間内総トランザクション数を増やす）。citeturn13view1  
  4. 走査後、最後の区間についても同様に閾値判定し、満たせば `tp[k]` に追加。citeturn13view1  
  5. `tp[k]` が空でなければ `{ik, tp[k]}` を `L1` に追加し、`L1` を得る。citeturn13view1  

- 手順（k≥2：Modified Apriori と Prune(Ck)）citeturn13view2turn16view3  
  1. `Ck = apriorigen(Lk-1)` で候補生成（通常Aprioriのjoinと同等）。citeturn13view2  
  2. `Prune(Ck)` では、候補 `si` の各 (k−1)-subset `d` を調べ、`d ∉ Lk-1` なら候補を除去。citeturn13view2  
  3. subsetが揃う場合、各subsetが持つ区間リストを用い、候補 `si` の区間リスト `tp[i]` を **「区間の全組合せ交差（pair-wise intersection）」で再構成**し、交差結果が空なら除去。citeturn13view2turn16view3  
  4. 交差後の区間リストから、`size < minthd2` を削除。citeturn13view2  
  5. `Ck` から `Lk` を計算する際は、「L1と同じ手順」を候補集合に対して適用できる、と述べています（具体的なループ展開は紙面からは確定しません）。citeturn13view2  

**区間出力の具体例（LPFIMは区間を直接出力）**  
論文定義に従えば、出力は概ね「`itemset -> list[[start,end], ...]`」です。citeturn13view0turn13view1  
例（説明目的の最小例：区間の表現形式だけを示す。数値は例示）：  
- あるアイテムXの出現時刻が `2,3,10,11` で、`minthd1` が「出現間隔の許容上限」を意味するため `3→10` で分断される場合、`X` の区間リストは `[[2,3],[10,11]]` のようになります（閉区間）。citeturn13view0turn13view1  

```mermaid
flowchart TD
  A[時刻順にDBを走査] --> B{Xが出現?}
  B -- yes --> C{lastseen==0?}
  C -- yes --> D[firstseen=lastseen=tm<br/>itemcount=transcount=1]
  C -- no --> E{tm-lastseen < minthd1 ?}
  E -- yes --> F[lastseen=tm<br/>itemcount++<br/>transcount++]
  E -- no --> G[直前区間を閉じる: [firstseen,lastseen]]
  G --> H{長さ>=minthd2 かつ support>=σ ?}
  H -- yes --> I[tpに区間追加]
  H -- no --> J[破棄]
  I --> K[新規区間開始: firstseen=lastseen=tm<br/>itemcount=transcount=1]
  J --> K
  B -- no --> L[transcount++]
  F --> A
  D --> A
  K --> A
  L --> A
```

### 未確定事項

LPFIMの一次情報だけでは、次の点が**仕様として一意に確定できません**（候補解釈を列挙し、次節で推奨案を提示します）。citeturn13view0turn13view1turn13view2  

**minSup（σ）判定式の一貫性**  
論文本文では「局所supportは比率」と書きつつ、頻出判定で `Sup_{[t1,t2]}(X) ≥ (σ/100)*tc` とも書かれています。citeturn13view0turn19view1  
一方、Algorithm 4.1 では `itemcount/transcount*100 ≥ σ`（百分率比較）を使っています。citeturn13view1  
このため、最小supportの単位が「比率」なのか「件数」なのかが本文だけでは整合しません。

| 論点 | 解釈候補 | 根拠（一次情報） | 実装への影響 |
|---|---|---|---|
| σの単位 | 候補A: %（比率×100） | Algorithm 4.1が `itemcount/transcount*100 ≥ σ`、さらに「count percentage」という説明がある。citeturn13view1 | 実装は比率比較（/100）でOK |
|  | 候補B: 比率（0〜1） | 本文が「ratio」と定義している。citeturn13view0turn19view1 | σ入力を0〜1で扱う必要 |
|  | 候補C: 件数（最小件数） | 本文の `≥ (σ/100)*tc` は「比率×母数=件数」型にも読める（ただし定義と矛盾）。citeturn13view0 | 件数閾値に変換が必要 |

**同一タイムスタンプに複数トランザクションがある場合の扱い**  
- DBが「昇順に整列」とあるのみで、同一時刻が重複可能か、またその場合の順序・カウントがどうなるかは明記されません。citeturn13view0turn19view1  

**区間長 `end-start` の端点解釈**  
- 区間は閉区間ですが、長さを `end-start` と定義しているため、離散時刻（整数）で「含む長さ」を `end-start+1` とする流派とは異なります。どちらを採用すべきかは論文内では議論されません（定義上は `end-start` が確定）。citeturn13view0turn13view2  

**k≥2 の Lk の具体算出**  
- `Lk can be computed from Ck using the same procedure used for computing L1` とありますが、候補itemsetごとに何を保持し、どのループで更新するかの詳細は紙面からだけでは確定できません。citeturn13view2  

### 推奨実装方針

以下は「不確定点を含む一次情報」を前提に、**再現可能性を最大化する推奨解釈**です（推奨＝設計判断であり、原典に明記された“唯一解”ではありません）。citeturn13view0turn13view1turn13view2  

**推奨解釈（support/σ）**  
- σは **百分率（0〜100）** として扱い、局所supportは  
  \[
  100 \times Sup_{[t_1,t_2]}(X) \ge \sigma
  \]
  を頻出条件とするのが最も首尾一貫します（Algorithm 4.1と本文の「count percentage」説明に整合）。citeturn13view1turn13view0  
- 本文の `Sup_{[t1,t2]}(X) ≥ (σ/100)*tc` は、比率定義と整合しないため **未確定（誤植候補）**として扱い、再現実装では採用しない方針を推奨します。citeturn13view0turn13view1  

**推奨データ型・前処理**  
- タイムスタンプは Python 側では `int`（離散時刻）か `datetime`（連続時刻）を許容しつつ、**差分計算（tm-lastseen）**が定義できる型に制約します。citeturn13view1turn19view0  
- 1トランザクション内の重複アイテムは、原論文が「subset」として扱うため **集合化（dedup）**を推奨します。citeturn13view0turn19view1  
- 同一タイムスタンプに複数トランザクションがある場合は一次情報で確定できないため、実装方針としては  
  - 推奨：入力検証で「同一時刻が複数ある場合は入力順を保持したまま処理（安定ソート）」とし、`tm-lastseen=0` を自然に扱う（`0 < minthd1` で同一区間に吸収されやすい）。citeturn13view1  
  - ただしこれは推奨解釈であり、原典の明記仕様ではありません（未確定点）。citeturn13view0  

**k≥2 の実装についての現実的推奨**  
- まず再現性を優先し、論文が明示する **「区間リスト交差によるPrune」**までは忠実実装します。citeturn13view2turn16view3  
- `Lk` 算出（候補の支持率・区間更新）の詳細が紙面だけでは曖昧なため、再現実装では以下の2段階方式が堅実です：  
  1. **候補itemsetごとに出現時刻列（occurrence timestamps）を構築**し、`minthd1` を用いた「区間分割」を occurrences 上で行う（Algorithm 4.1の考え方を一般化）。citeturn13view1  
  2. 各区間 [start,end] の支持率は、区間内トランザクション総数を分母、区間内でitemsetを含むトランザクション数を分子として評価（局所support定義に忠実）。citeturn13view0turn19view1  
- この方式は「Algorithm 4.1の精神（ギャップで区間を切る＋区間内出現率判定）」と「局所support定義」を同時に満たすため、推奨します。citeturn13view0turn13view1  

## PPFPM/GPF-growth（Kiran et al., JSS 2017: “Discovering partial periodic-frequent patterns in a transactional database”）

### 確定事項

**一次情報（必須URL）**  
- 原論文PDF（著者所属ページの公開PDF）: `https://www.tkl.iis.u-tokyo.ac.jp/new/uploads/publication_file/file/774/JSS_2017.pdf` citeturn6view0  
- 論文内DOI表記: `http://dx.doi.org/10.1016/j.jss.2016.11.035` citeturn26view0  

**公式/著者実装（一次実装の所在とライセンス）**  
- Pythonライブラリ **PAMI** に、GPF-growth実装（モジュールコード）が含まれ、当該JSS論文をReferenceとして明記しています。citeturn17view0turn10view0  
  - PAMI GitHub（GPL-3.0）: `https://github.com/UdayLab/PAMI` citeturn10view1  
  - PAMI PyPI（Author: Rage Uday Kiran / GPLv3表記）: `https://pypi.org/project/pami/0.9.7.2.9.2.9/` citeturn10view2  
  - PAMI GPFgrowth module code（GPL条項と著作権表記、論文参照が同居）: `https://pami-1.readthedocs.io/en/latest/_modules/PAMI/partialPeriodicFrequentPattern/basic/GPFgrowth.html` citeturn17view0turn10view0  
- PAMI側クレジットとして「Nakamuraが書き、Tarun Sreepadaが改訂、Rage Uday Kiran監督」と記載があります（ただし、これが2017論文の“原著者実装”と同一であるかは一次情報だけでは断定できません）。citeturn17view2  

**入力形式（問題設定の入力）**  
- 取引DBは `TDB = {tr1,...,trm}` で、各トランザクションは `tr_k = (ts, Y)`（tsがタイムスタンプ、Yがアイテム集合）として定義されます。citeturn8view0turn15view0  
- パターンXの出現時刻列 `TS_X` は、Xが出現したタイムスタンプの**順序付き集合（ordered set）**として定義されています。citeturn15view0turn25view1  
- 例題では「各トランザクションはタイムスタンプで一意に識別できる」と明記され、また**欠損タイムスタンプ（例：ts=5）も周期性評価に寄与する**と述べています。citeturn15view2turn8view0  
- 本論文の対象は「temporally ordered transactional database」と記述されています。citeturn15view1  

**出力形式（区間表現の扱いも明記）**  
- 出力は **partial periodic-frequent patterns（アイテムセット）**の集合で、各パターンについて少なくとも **supportとperiodic-ratio** が定義されます。citeturn21view0turn14view0  
- 論文は、表・説明内で “partial periodic-frequent patterns” を `{pattern: support, periodic-ratio}` の形式で表す、と明示しています（機械可読なファイルフォーマット仕様ではなく、表記法）。citeturn24view0  
- **区間 [start,end] の出力は本モデルには存在しません**（periodic-ratioは「周期的に繰り返した“回”の割合」であって、局所頻出区間を列挙する枠組みではない）。周期は差分列として扱われます。citeturn21view0turn25view0  

**support / periodicity / ratio の厳密定義（端点の扱い含む）**  
本論文は「端点periodを含むperiod列」を明確に定義しています。citeturn25view0turn21view0  

- **support（件数）**  
  \[
  sup(X) = |TS_X|
  \]
  （TS_XはXが出現したタイムスタンプ列）citeturn8view0turn7view0  

- **period列（端点を含む）**  
  `TS_X = {ts_a^X,...,ts_c^X}` に対し、periodは  
  \[
  p^X_1 = ts^X_a - ts_{ini},\ \ ts_{ini}=0
  \]
  \[
  p^X_k = ts^X_q - ts^X_p \ (1<k<sup(X)+1)
  \]
  \[
  p^X_{sup(X)+1} = ts_{fin} - ts^X_c
  \]
  と定義され、`|P_X| = sup(X)+1` が成立します。citeturn25view0turn14view1  
  例として ‘ab’ のperiod列を端点込みで計算する Example 5 が明示されています。citeturn25view0  

- **periodicity（最大period）**  
  \[
  periodicity(X)=\max(P_X)
  \]
  citeturn25view0turn21view0  

- **interesting period（maxPer）**  
  \[
  p\in IP_X \iff p\in P_X \land p \le maxPer
  \]
  citeturn8view1turn21view0  

- **periodic-ratio（PR）**  
  \[
  PR(X)=\frac{|IP_X|}{|P_X|}
  \]
 （0〜1）citeturn21view0  

- **partial periodic-frequent pattern**  
  \[
  sup(X)\ge minSup \ \land\ PR(X)\ge minPR
  \]
  のとき、Xをpartial periodic-frequent と定義。citeturn7view1turn14view0turn21view0  

**擬似コード（論文Algorithm 1〜6の要点）**  
論文は、(i)候補アイテム抽出（GPF-list）、(ii)GPF-tree構築、(iii)ボトムアップ再帰採掘（prefix-tree/conditional-tree）を含む GPF-growth を提示します。citeturn23view3turn24view0turn20view2  

- **Algorithm 1: GPF-list（候補CIの抽出）**  
  - `tsl[i]`（最後の出現時刻）と `ip[i]`（interesting periods数）、`s[i]`（support）を更新し、`minSup, maxPer, minPR` を用いて候補アイテム集合CIを得る、と説明されています。citeturn23view3turn20view3  

- **Algorithm 2-3: GPF-tree（prefix-tree＋tail-nodeにts-list保持）**  
  - CI順に各トランザクション内アイテムをソートし、FP-treeに似たprefix-treeを作るが、**supportはノードに持たず**、末端（tail-node）にts-listを保持することが説明されています。citeturn20view2turn23view2turn22view0  

- **Algorithm 4-6: 再帰採掘とPR算出**  
  - ヘッダの末尾側アイテムからprefix-tree（PT_i）→条件付き木（CT_i）→拡張パターンのTS配列を作ってPR評価、というボトムアップ採掘を記述しています。citeturn22view0turn24view0turn20view0  
  - また、条件付きパターンベース等の表記法（`{nodes: ts-list}` 等）も本文中で定義されています。citeturn24view0  

```mermaid
flowchart TD
  A[入力: temporally ordered TDB] --> B[1パス目: GPF-list作成<br/>S, IP, tsl更新]
  B --> C[候補CIへ枝刈り<br/>sup>=minSup かつ IP>=minPR*(minSup+1)]
  C --> D[2パス目: GPF-tree構築<br/>CI順に各トランザクション挿入<br/>tail-nodeにts-list]
  D --> E[GPF-growth 再帰採掘<br/>suffix itemごとにprefix-tree→conditional-tree]
  E --> F[拡張パターンのTSを復元]
  F --> G[periodic-ratio=|IP|/|P| を計算]
  G --> H[条件 sup>=minSup かつ PR>=minPR を満たすパターンを出力]
```

### 未確定事項

GPF-growthは一次情報が豊富ですが、**擬似コードの一部に定義式・例と整合しない可能性**が見られます。原論文だけからは「誤植か否か」を断定できないため、ここでは**未確定**として、候補解釈と推奨修正を併記します。citeturn23view3turn22view1turn25view0turn21view0  

| 箇所 | 論文の見え方（一次情報） | 未確定ポイント | 候補解釈 |
|---|---|---|---|
| Algorithm 1 の `ip` 更新 | `if (tscur-tsl)<=maxPer then ip++` の後に、さらに `Update si++, ipi++` があるように読める citeturn23view3 | ipが「interesting periods数」なら二重計上になり、本文例（S,IP更新の説明）とも矛盾し得る citeturn23view0 | 候補A: 行14の `ipi++` が誤植（本来は `si++` のみ） / 候補B: ipは別指標（ただし本文は“interesting periods”と説明）citeturn23view3turn20view3 |
| Algorithm 1 の support枝刈り条件 | `if si ≤ minSup then remove` のように読める citeturn23view3 | 定義上 frequent は `sup≥minSup` citeturn7view1turn8view0 | 候補A: `si < minSup` が正 / 候補B: 論文中の minSup は「厳密に超える」定義（ただし定義2は≥）citeturn7view1 |
| Algorithm 5/6 の末尾端period | `TS[last] - ts_f ≤ maxPer` の形に読める citeturn22view1 | 定義3では末尾端periodは `tsfin - TS[last]` citeturn25view0 | 候補A: 符号が誤植で `ts_f - TS[last]` / 候補B: ts_f の定義が逆（だがAlgorithm 5行1はts_f=tsmと記述）citeturn22view1 |
| Algorithm 4 の再帰条件 | `if Treeβ = ∅ then call GPF-growth(Treeβ,β)` と読める citeturn24view0 | 通常は非空のとき再帰するのが自然 | 候補A: `Treeβ ≠ ∅` の誤植 |
| 複数トランザクション/同一タイムスタンプ | 例では「各トランザクションはtsで一意」とある citeturn15view2 | 一意性が前提仕様か、単なる例の前提かが確定しない | 候補A: tsは一意（同時刻は不可）/ 候補B: 同時刻は許容し、同一ts上で複数トランザクションを並べる |

### 推奨実装方針

**推奨の優先順位：定義式・例（Example 5等）＞ 擬似コードの逐語**  
- period列の端点処理は、Definition 3 と Example 5 により **`tsini=0` と `tsfin` を用いて `P_X` を作る**ことが具体計算で確認できます。従って実装は定義式に合わせ、  
  \[
  P_X = diff([ts_{ini}] + TS_X + [ts_{fin}])
  \]
  を採用するのが推奨です。citeturn25view0turn14view1  
- interesting periods数は `count(p ≤ maxPer)`、PRは `|IP_X|/|P_X|` に固定し、擬似コードの符号問題は **誤植候補として補正**するのを推奨します。citeturn21view0turn22view1  

**同一タイムスタンプの扱い（推奨＝設計判断）**  
- 論文例はts一意を前提にしているため、再現性重視なら「ts一意」を入力制約にするのが最も安全です。citeturn15view2turn8view0  
- ただし実務上どうしても同時刻が発生するなら、推奨実装では「同一tsを許容し、TS_Xは重複tsを含む多重集合として扱う」か「同時刻を安定に並べ替えて擬似的に別tsへ展開」など、明示的な前処理ポリシーを設ける必要があります（一次情報だけでは確定不可）。citeturn15view2turn21view0  

**minSup の単位**  
- 定義上 support は件数であり、minSupも基本的に件数閾値として扱うのが素直です。citeturn7view0turn7view1turn21view0  
- 論文は「supportやperiodicityを( tsfin-tsini )に対する割合で表すことも可能」と述べますが、説明は件数ベースで行っています。citeturn21view0  
- そのため再現実装では「外部APIとしてminSupは count を基本」とし、比率入力を許可する場合は「`minSup_count = ceil(minSup_ratio * |TDB|)`」等を**実装側の仕様**として別途定義するのが推奨です（原典に一意規定はありません）。citeturn8view0turn21view0  

**PAMI実装を参照する場合の注意（再現検証用途）**  
- PAMIはGPF-growthのReferenceとしてJSS 2017論文DOIを明記し、GPLv3で公開されています。citeturn17view0turn10view1turn10view2  
- ただしPAMI実装では、入力ファイルを「1行＝`timestamp item1 item2 ...`（デフォルト区切りはタブ）」として読み、先頭カラムを `int(line[0])` でタイムスタンプとして扱っています。citeturn12view2turn18view0turn12view1  
- またPAMIは minSup がfloat（比率）で与えられた場合に、内部で `value = (maxTS * value)` の形でcountへ変換しています（maxTS＝最大タイムスタンプ）。これは `|TDB|` ではなく **最大時刻に依存**するため、欠損タイムスタンプがあるケースで論文定義（support＝件数）とずれる可能性があります。citeturn17view2turn18view0  
- period/interesting periodsの数え上げは、`[0, maxTS]` を加えた上で差分を取り、`diff<=maxPer` の個数を数える実装になっており、Definition 3/7 と整合する方向です。citeturn18view1turn25view0turn21view0  

## Python再現実装チェックリスト

### 前処理

**共通（LPFIM/GPF-growth）**  
- 入力を「時刻付きトランザクション列」に正規化：`[(ts, set(items)), ...]`。時刻順にソート（安定ソート）。citeturn19view1turn15view1  
- 1トランザクション内の重複アイテムを除去（集合化）。citeturn19view1turn8view0  
- タイムスタンプ差分が計算できる型か検証（LPFIMのminthd1判定、GPF-growthのperiod差分）。citeturn13view1turn25view0  

### コアデータ構造

**LPFIM**（推奨）  
- `Interval = (start, end)`（閉区間）  
- `interval_list: list[Interval]`（start昇順）  
- `itemset -> interval_list` の辞書（Lk保持）  
- `intersect_interval_lists(A,B)`（全組合せ交差を返し、`end-start>=minthd2` でフィルタ）citeturn13view2turn13view0  

**GPF-growth**  
- `TS[item] = sorted(list_of_timestamps)`（単一アイテム）citeturn8view0turn7view0  
- period計算関数：`periods = diff([0] + TS + [ts_fin])`、`ip = count(p<=maxPer)`、`PR=ip/(len(TS)+1)` citeturn25view0turn21view0  
- GPF-treeノード：`children: dict[item, node]`, `parent`, `node_link`（同item連結）, `ts_list`（tail-nodeに保持）citeturn20view2turn20view1turn23view2  
- `GPF-list`（候補アイテム管理：S, IP, tsl）citeturn23view3turn20view3  

### 実装すべき主要関数

**LPFIM**  
- `scan_L1(transactions, minthd1, minthd2, sigma) -> dict[item, intervals]`（Algorithm 4.1の再現）citeturn13view1  
- `apriori_gen(Lk_minus_1)`（通常Apriori join）citeturn13view2  
- `prune_candidates(Ck, Lk_minus_1, minthd2)`（subset存在＋区間交差による枝刈り）citeturn13view2turn16view3  

**GPF-growth**  
- `calc_PR(TS, maxPer, ts_fin) -> (support, ip_count, pr)`（Definition 3/7に基づく）citeturn25view0turn21view0  
- `build_GPF_list(TDB, minSup, maxPer, minPR) -> CI`（Algorithm 1の意図に基づき、ただし不整合箇所は定義式ベースで補正）citeturn23view3turn14view2  
- `build_GPF_tree(TDB, CI)`（Algorithm 2-3の再現）citeturn23view2turn20view2  
- `mine_GPF_tree(tree, alpha)`（Algorithm 4の再帰、PT/CT構築、TS復元、PR判定）citeturn24view0turn22view0  

### 検証テスト（論文例に対する合否判定）

**GPF-growth（最優先で自動テスト化推奨）**  
- Table 1相当の入力（例題DB）を作り、`TS_ab={2,4,6,7,9,11,12}`、`sup(ab)=7` を満たす。citeturn8view0turn25view0  
- Example 5のperiod列 `P_ab={2,2,2,1,2,2,1,1}` を再現できる（端点period含む）。citeturn25view0  
- Definition 7の例：`PR(cd)=5/6=0.833...` を再現できる。citeturn21view0  
- Table 2/3記載の（support,PR）表記 `{pattern: support, periodic-ratio}` の値と整合する（しきい値設定を論文例に合わせる）。citeturn25view0turn24view0  

**LPFIM**  
- 閉区間 `t1 ≤ t ≤ t2` の判定が実装で保たれている。citeturn13view0  
- minthd1境界（`< minthd1`）で区間分割が変わることをテスト（等号時に新規区間になるか）。citeturn13view1  
- 出力区間が `[start,end]` で、長さが `end-start` として扱われている（minthd2フィルタに反映）。citeturn13view0turn13view2