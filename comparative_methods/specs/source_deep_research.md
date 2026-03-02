# 合成トランザクション時系列データ向け 8手法の再現実装仕様を確定するための一次情報調査

## 前提と比較設計

本タスクでは、入力データを「時刻付きトランザクション列」として扱う前提を置く。すなわち、各トランザクションは **(timestamp, itemset)**（同一時刻に複数トランザクション可）であり、全体はタイムスタンプ昇順に整列された列である。これは、局所周期パターン（LPP）側が「タイムスタンプ順の temporal database（離散列）」を定義しているためである。citeturn31view1turn32view0

比較タスクは２系統に分かれる。

- **パターン同定比較（Apriori / FP-Growth / Eclat / LCM）**  
  これらは基本的に「トランザクション集合（transaction database）」上の頻出アイテム集合（frequent itemsets）を出力する枠組みであり、タイムスタンプは定義上の入力に含まれない（または無視される）。FP-Growth は transaction database と minsup を入力として頻出パターン集合を出力する仕様で記述されている。citeturn22view0turn23view3  
  Eclat は TID-list（tid-list）に基づく頻出アイテム集合の列挙であり、扱うのは「transaction identifier」の集合（tid-list）であって「時間区間」ではない。citeturn25view0turn26view1  
  LCM の公式 README でも、列挙対象は frequent / closed / maximal itemsets であり、出力形式も itemset と frequency（件数）である。citeturn19view0  
  よって **これら４手法は「区間（interval）の直接出力」には非対応**であり、区間検出と横並び比較する際は「同じ出力型ではない」点を明示して比較設計する必要がある（例：区間検出側は「パターン＋区間リスト」を出すのに対し、FIM 側は「パターン＋support」のみ）。citeturn19view0turn23view3turn25view0

- **区間検出比較（LPFIM / LPPM、必要に応じ PFPM / PPFPM）**  
  LPFIM は、ローカルに頻出な itemset を「頻出となる time interval のリスト」と結びつけて保持する、という出力設計が一次情報に明示されている。citeturn18view0  
  LPPM（LPPM_breadth / LPPM_depth / LPP-Growth）は、LPP（Local Periodic Pattern）を「periodic time-interval(s)」とともに出力することが、問題定義・定義式・例のレベルで明記されている。citeturn15view0turn16view3turn32view0turn30search1  
  一方、PFPM と PPFPM は「（部分）周期頻出」を主眼とし、**基本的に全データ範囲に対する周期性指標（period list / periodicity / periodic-ratio 等）で判定してパターンを出す**枠組みで、LPPM のように「非事前定義の time-interval の列挙」を出力仕様としていない（後述）。citeturn14view0turn29search3turn11view1turn10view0

## 手法別の一次情報と再現実装仕様

以降、手法ごとに A〜H を揃える。各手法の冒頭に「一次情報 URL（原論文／公式ドキュメント／公式実装）」を明記し、本文中の仕様記述は該当一次情報に紐づけて引用する。

### Apriori

**一次情報 URL**
- 原論文（Apriori / AprioriTid を含む）: `https://www.vldb.org/conf/1994/P487.PDF` citeturn20view0turn21view1
- 公式ドキュメント（SPMF Apriori）: `https://www.philippe-fournier-viger.com/spmf/Apriori.php` citeturn29search0

**A. 問題設定（入力・出力）**  
原論文では、transaction set D（各 transaction は items の集合、TID 付き）と minsup / minconf を入力として、(1) minsup 以上の itemsets（large itemsets）を見つけ、(2) それらから minconf を満たす association rules を生成する、という二段階に分解している。citeturn20view0  
本タスクの「パターン同定比較」では、このうち (1) の frequent itemsets 列挙（large itemsets discovery）を出力として扱うのが自然である。citeturn20view0

**B. 厳密な定義（support 等）**  
- transaction database: 各 transaction T は items の集合で、X ⊆ T なら T は X を含む。citeturn20view0  
- support（ルール X⇒Y のサポート）: D のうち X∪Y を含む transaction の割合（%）として定義されている。citeturn20view0  
- large itemset 判定では「support は itemset を含む transaction 数（count）」として述べ、minsup を満たす itemsets を large と呼ぶ、としている。citeturn20view0  
（※この論文中では “support” を「%」と「count」の両方の文脈で説明しているため、再現実装では **count か ratio かの統一**が必要。SPMF 例では minsup を「割合（%）」で与えつつ、判定は transaction 数に基づく説明になっている。citeturn20view0turn29search0）

**C. パラメータ一覧**  
- minsup: 最低サポート。large itemsets の閾値。citeturn20view0turn29search0  
- minconf: ルール生成閾値（本タスクでは通常未使用）。citeturn20view0  
推奨範囲・デフォルト: **未確定**（原論文・SPMF 文書に一般的な推奨範囲やデフォルトの明記なし）。citeturn20view0turn29search0

**D. 擬似コードまたは実装手順（再現粒度）**  
原論文は Apriori の候補生成（apriori-gen）と反復探索を提示している。citeturn21view3turn21view1  
再現実装の要点は以下。
- k=1 で各単品の support count を数え L1 を得る。citeturn21view0  
- k≥2:  
  1) L(k-1) から apriori-gen で候補 Ck を生成（join + prune）。citeturn21view3turn21view1  
  2) DB を scan して Ck の count を加算し、minsup 以上を Lk とする。citeturn21view3turn21view0  
- Lk が空になったら終了し、∪k Lk を出力する。citeturn21view3

**E. 計算量（時間・メモリ）**  
一般形の漸近計算量は **未確定**（原論文に「O(…)」の形での一般式提示なし）。ただし「multiple passes over the data」「candidate itemsets を生成して数える」という設計は明記されている。citeturn20view0turn21view0

**F. 既存実装の有無、実行方法、ライセンス**  
- entity["organization","SPMF","pattern mining library"] に Apriori 実装がある（例ページが存在）。citeturn29search0  
  ライセンス: SPMF 全体は GNU GPL v3 と明記されている。citeturn6search2turn6search14

**G. 再現実装時の落とし穴**  
- item の重複: SPMF では「同一トランザクション内で同一 item が二度出てはいけない」と明示されている。citeturn27search1turn29search21turn29search3  
- ソート: SPMF の複数アルゴリズムの前提として、transaction 内 item は total order（例：昇順）でソートされる想定が書かれている。citeturn29search3turn30search1  
- minsup の単位（% vs count）: 原論文は % 表現と count の説明が混在しうるため、比較系では **内部表現を count に統一**し、入出力で % 指定を許すなら変換を固定する設計が必要。citeturn20view0turn29search0

**H. このタスク向け適合性**  
パターン同定: 適（頻出 itemset のベースラインとして）。citeturn20view0turn29search0  
区間検出: 不適（区間の定義や出力を扱わない）。citeturn20view0  
ミスマッチ: 時系列性（非定常・局所性）の比較には直接使えないため、「同一データ上でタイムスタンプを落として頻出性だけを見る」位置づけが必要。citeturn20view0turn31view1

### FP-Growth

**一次情報 URL**
- 原論文（FP-tree, FP-growth）: `https://www.cs.sfu.ca/~jpei/publications/sigmod00.pdf` citeturn22view0turn23view3turn24view1
- 公式ドキュメント（SPMF FPGrowth）: `https://www.philippe-fournier-viger.com/spmf/FPGrowth.php` citeturn27search1

**A. 問題設定（入力・出力）**  
transaction database DB と minimum support threshold を入力し、「complete set of frequent patterns」を出力する、と明記されている。citeturn22view0turn23view3

**B. 厳密な定義（support 等）**  
support（occurrence frequency）は「DB 内でパターン A を含む transaction 数」と定義し、support ≥ threshold のとき frequent pattern と定義している（絶対度数としての support を明示）。citeturn22view0

**C. パラメータ一覧**  
- minsup（論文中の記号 ϕ）: minimum support threshold。citeturn22view0turn24view1  
推奨範囲・デフォルト: **未確定**（原論文・SPMF 文書に一般的推奨やデフォルトの固定値記載なし）。citeturn22view0turn27search1

**D. 擬似コードまたは実装手順（再現粒度）**  
FP-tree 構築手順（Algorithm 1）と、FP-growth による再帰採掘（Algorithm 2）が提示されている。citeturn24view1turn23view3  
再現実装の要点は以下。
- DB を１回走査して frequent items と support を集計し、support 降順に並べたリスト L を作る。citeturn24view1  
- 各 transaction から frequent items のみを抜き、L の順に並べて FP-tree に挿入し、ノード count を更新する。citeturn24view1  
- FP-growth（Algorithm 2）:  
  - tree が single path の場合、ノード組合せを列挙し support は該当ノードの最小 count とする。citeturn23view3  
  - それ以外は header table の各 item ai について conditional pattern base を作り、conditional FP-tree を作って再帰する。citeturn23view2turn23view3

**E. 計算量（時間・メモリ）**  
一般形 O(…) は **未確定**（原論文に単一の漸近式が固定提示されていない）。ただし以下は一次情報として明言できる。
- FP-tree のサイズは DB サイズにより上界づけられ、「指数的ノード数の FP-tree は生成されない」と記述されている。citeturn24view2  
- 一方で、頻出パターン数自体は指数的になり得る（例として長さ100の頻出パターンから非常に大量の頻出パターンが生成され得る旨の説明）。citeturn23view1

**F. 既存実装の有無、実行方法、ライセンス**  
- SPMF に FP-Growth 実装がある。citeturn27search1turn29search6  
  ライセンスは GNU GPL v3。citeturn6search2turn6search14  
- 参考（公式実装の別系統）として、Borgelt の FP-growth ドキュメントが公開されている（ただし本タスクでは SPMF を「公式実装候補」として優先）。citeturn27search7

**G. 再現実装時の落とし穴**  
- support は絶対度数（count）で定義されている点（割合換算は比較系で明示的に）。citeturn22view0  
- transaction 内 item の重複禁止・ソート前提は SPMF 側で明示されている。citeturn27search1turn29search21  
- 「conditional pattern base / conditional FP-tree」生成の細部（prefix path 抽出、count 付与）を原論文の定義に合わせないと support がズレる。citeturn23view2turn23view3

**H. このタスク向け適合性**  
パターン同定: 適（高速な頻出 itemset 列挙）。citeturn23view3turn27search1  
区間検出: 不適（time-interval を出さない）。citeturn23view3

### Eclat

**一次情報 URL**
- 原論文（Eclat を含む垂直表現の体系）: `https://www.philippe-fournier-viger.com/spmf/zaki2000.pdf` citeturn28search11turn26view1
- 公式ドキュメント（SPMF Eclat/dEclat）: `https://www.philippe-fournier-viger.com/spmf/Eclat_dEclat.php` citeturn29search1

**A. 問題設定（入力・出力）**  
原論文は「frequent itemsets の発見が association mining の計算集約部である」とし、垂直形式（各 item の tid-list）で support を交差（intersection）で求める枠組みを説明する。citeturn25view0turn28search11  
SPMF の Eclat も「transaction database と minsup を入力し frequent itemsets を出力」と説明している。citeturn29search1

**B. 厳密な定義（support 等）**  
- tid-list: item X の tid-list L_X は「X を含む transaction identifier のリスト」。citeturn25view0  
- support: itemset の support は tid-list intersection の結果の cardinality（|L_X|）で得られる、という支え（Lemma）が示されている。citeturn25view0turn26view1

**C. パラメータ一覧**  
- minsup: 最低 support（count）。citeturn29search1turn26view1  
推奨範囲・デフォルト: **未確定**（一次情報に一般推奨値の固定記載なし）。citeturn29search1turn28search11

**D. 擬似コードまたは実装手順（再現粒度）**  
原論文は「vertical tid-list format により、support を tid-list intersection で判定できる」点、およびクラス分割・探索戦略（bottom-up / top-down 等）を示す。citeturn25view0turn26view1turn26view2  
再現実装（Python）として最小限必要な手順は次。
- 1-itemset: 各 item の tid-list を構築し support=|tid-list| を計算。citeturn25view0turn26view1  
- DFS（典型的 Eclat）: prefix P を拡張する候補 item を順序付けし、P∪{i} の tid-list を intersection で得て、support ≥ minsup のとき再帰探索。  
（※この DFS 形は “tid-list intersections による列挙” という一次情報の中核に沿うが、クラス分割（equivalence classes）等の詳細をフル再現する場合は原論文の class/sublattice 処理まで実装対象に含める必要がある。citeturn26view3turn28search11）

**E. 計算量（時間・メモリ）**  
一般形 O(…) は **未確定**（単一漸近式の提示なし）。ただし「tid-list の intersection により support counting を行う」「tid-list は上位へ行くほど縮むため intersection が速くなる」旨の性質が述べられている。citeturn26view1

**F. 既存実装の有無、実行方法、ライセンス**  
- SPMF に Eclat 実装あり。citeturn29search1turn29search6  
  ライセンス GNU GPL v3。citeturn6search2turn6search14

**G. 再現実装時の落とし穴**  
- tid-list の整合: transaction ID（TID）の付番と順序が stable でないと、intersection 結果の再現性が崩れる（定義上 tid-list は TID の集合）。citeturn25view0  
- 時刻との混同: tid-list は “transaction identifiers” であって “timestamp” ではないため、Eclat 単体では time-interval を表現しない。citeturn25view0turn29search1

**H. このタスク向け適合性**  
パターン同定: 適（垂直表現の代表）。citeturn26view1turn29search1  
区間検出: 不適（区間を出さない）。citeturn25view0

### LCM

**一次情報 URL**
- 公式実装（README/Usage/Output/設計説明）: `https://research.nii.ac.jp/~uno/code/lcm.html` citeturn19view0
- 公式ドキュメント（SPMF LCMFreq）: `https://www.philippe-fournier-viger.com/spmf/LCMFreq.php` citeturn29search2

**A. 問題設定（入力・出力）**  
公式 README では、transaction database D（各 record は itemset）に対し、support（frequency）閾値 t を与えて frequent itemsets を列挙する。さらに frequent itemsets のうち maximal / closed の列挙も扱い、LCM がそれらを enumerate（output または count）する、と明確に述べている。citeturn19view0

**B. 厳密な定義（support 等）**  
- frequency（support）: itemset を含む transaction 数。citeturn19view0  
- closed: 同一 frequency の上位集合が存在しない itemset。maximal: いかなる他の frequent itemset にも含まれない itemset。citeturn19view0

**C. パラメータ一覧**  
- support（minimum support）: 閾値 t（transaction 数）。citeturn19view0  
- 実装オプション: ver.4/5 の `lcm [command] [options] input-filename support [output-filename]` 形式、および item constraints 用の `-c/-C` 等が説明されている。citeturn19view0  
推奨範囲・デフォルト: **未確定**（support の推奨範囲はデータ依存、README に固定推奨なし）。citeturn19view0

**D. 擬似コードまたは実装手順（再現粒度）**  
公式 README に「基本は depth-first search」であること、重複回避（j > tail(I)）の再帰列挙骨格、および conditional database（D(I)）とメモリ管理（生成した transaction を再帰終了後に削除し、メモリを安定化）等の実装論が記述されている。citeturn19view0  
Python 再現の観点では、LCM を“アルゴリズム仕様どおりに Python で書き直す”よりも、公式 C 実装（または同系統実装）を呼び出す方が現実的になりやすい（理由は後段「Python実装方針」）。citeturn19view0turn29search2

**E. 計算量（時間・メモリ）**  
一般形 O(…) は **未確定**。ただしメモリについては「生成トランザクションの削除により transaction 用メモリを database サイズの 2 倍程度に抑える」趣旨の説明がある。citeturn19view0

**F. 既存実装の有無、実行方法、ライセンス**  
- 公式実装（lcm.html）にコンパイル方法（make）と CLI 形式、出力形式（各行 item 列＋必要なら frequency）などが記載されている。citeturn19view0  
- SPMF に LCMFreq として “LCM family で frequent itemsets を掘る実装”がある。citeturn29search2

ライセンス:  
- SPMF は GNU GPL v3。citeturn6search2turn6search14  
- LCM 公式実装のライセンス表記は、この調査範囲（lcm.html 抜粋）内では **未確定**（ページ内に明確な OSS ライセンス条文の明示を確認できていないため）。citeturn19view0

**G. 再現実装時の落とし穴**  
- 「frequent / closed / maximal」どれを比較対象にするかを固定しないと、Apriori/FP-Growth/Eclat と出力集合が一致しない（LCM は複数列挙モード）。citeturn19view0turn29search2  
- 出力フォーマット差（frequency の出力位置など）をパーサで吸収する必要がある。citeturn19view0

**H. このタスク向け適合性**  
パターン同定: 適（高速系の代表候補。SPMF 側も「高速」と位置づけ）。citeturn29search2turn19view0  
区間検出: 不適（出力は itemset と frequency）。citeturn19view0

### PFPM

**一次情報 URL**
- 原論文（PFPM preprint）: `https://www.philippe-fournier-viger.com/PFPM_mining_periodic_patterns.pdf` citeturn12view0turn14view0turn13view0
- 公式ドキュメント（SPMF PFPM）: `https://www.philippe-fournier-viger.com/spmf/PFPM.php` citeturn29search3

**A. 問題設定（入力・出力）**  
PFPM は、transaction database における periodic frequent patterns / periodic frequent itemsets を、最大周期だけに依存せず（min/avg/max periodicity を組合せ）見つける問題設定を置き、PFPM（Periodic Frequent Pattern Miner）というアルゴリズムを提示している。citeturn12view0turn14view0turn13view0  
SPMF の PFPM 文書では、出力は「frequent periodic itemset」ごとに support と periodicity 指標（#MINPER, #MAXPER, #AVGPER）を付与する形式である。citeturn29search3

**B. 厳密な定義（support, periodicity 等）**  
原論文における定義の核は以下。
- support: s(X)=|{t ∈ D ∧ X ⊆ t}|（g(X) は X を含む transaction 集合、s(X)=|g(X)|）。citeturn12view0  
- periods（ps(X)）: g(X) の transaction 番号（インデックス）差分の列として  
  ps(X) = {g1−g0, g2−g1, …, g_{k+1}−g_k}（g0=0, g_{k+1}=n）と定義。citeturn12view0  
- maxper(X)=max(ps(X)) を既存 periodicity 指標として紹介。citeturn12view0  
- minper(X)=min(ps(X)) については、先頭・末尾 period の扱いが不安定（0/1になり得る）ため「先頭と末尾 periods を除外し、それにより空なら minper=∞」という運用定義を置く。citeturn14view0  
- avgper(X) を導入し（定義式あり）、さらに minAvg ≤ avgper(X) ≤ maxAvg, minper(X) ≥ minPer, maxper(X) ≤ maxPer を満たすものを periodic frequent itemset と定義（Definition 5）。citeturn14view0

**C. パラメータ一覧**  
- minAvg, maxAvg: avgper(X) の許容範囲。citeturn14view0turn29search3  
- minPer, maxPer: minper(X), maxper(X) の閾値。citeturn14view0turn29search3  
- minsup: 明示パラメータではなく、avgper と |D| の関係（Theorem 2）から γ=(|D|/maxAvg)−1 を下界として剪定に使う設計が本文にある。citeturn13view0turn14view2  
推奨範囲・デフォルト: **未確定**（一次情報に “デフォルト値” の記載なし）。citeturn29search3turn14view0

**D. 擬似コードまたは実装手順（再現粒度）**  
PFPM は「tid-list に基づき Eclat に触発された」方式で、入力は DB と閾値群。citeturn14view2turn13view0  
本文から再現実装に必要な流れは次。
1) DB を走査して各 1-itemset の s({i}), minper({i}), maxper({i}) を計算。citeturn13view0turn14view2  
2) γ=(|D|/maxAvg)−1 を計算し、maxper≤maxPer かつ support≥γ の item を候補 I* とする（Theorem 1/2 pruning）。citeturn13view0turn14view2  
3) 候補 item の tid-list を構築し、DFS で tid-list intersection をしながら minper/maxper を更新して条件を満たす itemset を出力。citeturn13view0turn14view2  
（※Intersection 手続きは Algorithm 3 があると本文が言及している。citeturn13view0）

**E. 計算量（時間・メモリ）**  
一般形 O(…) は **未確定**。ただし、論文実験で「PFPM は Eclat よりメモリ使用が少ない観測があった」と述べている（詳細表は省略と明記）。citeturn13view2

**F. 既存実装の有無、実行方法、ライセンス**  
- SPMF に PFPM 実装があり、入出力フォーマット（各行 item 列の後に #SUP, #MINPER, #MAXPER, #AVGPER）が明示されている。citeturn29search3  
- ライセンス GNU GPL v3。citeturn6search2turn6search14

**G. 再現実装時の落とし穴**  
- **minper の扱い**: 先頭・末尾 period を除外し、空なら ∞ とする、という定義上の注意がある（ここを外すと minper が 0/1 に引きずられやすい）。citeturn14view0  
- SPMF 入力前提（重複禁止・ソート）は PFPM 文書にも明記。citeturn29search3

**H. このタスク向け適合性**  
パターン同定: 条件付きで適（「周期頻出」フィルタで頻出 itemset を絞る用途）。citeturn14view0turn29search3  
区間検出: **直接は不適**（出力仕様は itemset＋周期指標であり time-interval 列挙を含まない）。citeturn29search3turn14view0  
→ 区間が必要なら、PFPM の出力から区間を復元する後処理設計が必要だが、一次情報上「その区間出力方式」は定義されていないため、本調査の範囲では **未確定（後処理が必要）**となる。citeturn29search3turn14view0

### PPFPM（Partial Periodic-Frequent Pattern Mining）

**一次情報 URL**
- 原論文（partial periodic-frequent patterns / periodic-ratio / GPF-growth）: `https://www.tkl.iis.u-tokyo.ac.jp/new/uploads/publication_file/file/774/JSS_2017.pdf` citeturn9view0turn11view1turn10view0

**A. 問題設定（入力・出力）**  
本論文は「temporally ordered transactional database」上で partial periodic-frequent patterns を発見するモデルを提示し、periodic-ratio を導入して「周期反復の割合」で partial periodicity を判定する。citeturn9view0turn11view1  
出力例（Table 3 など）では pattern ごとに {pattern: support, periodic-ratio} 形式で表現されると説明されている。citeturn10view0turn11view1

**B. 厳密な定義（support, periodicity, periodic-ratio）**  
本論文のモデル定義は明確に式で与えられている。
- TS_X: itemset X が現れる timestamp の昇順リスト。citeturn11view0  
- support: sup(X)=|TS_X|（Definition 1）。citeturn11view0  
- periods P_X:  
  - 初回: p1 = ts_a − ts_ini（ts_ini=0）  
  - 中間: 連続出現の差分  
  - 最後: p_{sup(X)+1} = ts_fin − ts_c（ts_fin は DB 最終 timestamp）  
  として、|P_X|=sup(X)+1 の period list を定義（Definition 3 とその説明）。citeturn11view1  
- periodicity(X)=max(P_X)（Definition 4）。citeturn11view1  
- interesting period: p ≤ maxPer を満たす period（Definition 6）。citeturn11view1  
- periodic-ratio: PR(X)=|IP_X|/|P_X|（Definition 7）。citeturn11view1  
- partial periodic-frequent: PR(X) ≥ minPR を満たす frequent pattern（Definition 8）。citeturn11view1

**C. パラメータ一覧**  
- minSup: frequent 判定閾値。citeturn11view0  
- maxPer: period が “interesting” かの閾値。citeturn11view1  
- minPR: periodic-ratio の最低閾値。citeturn11view1  
推奨範囲・デフォルト: **未確定**（一次情報に一般推奨の固定値なし）。citeturn9view0turn11view1

**D. 擬似コードまたは実装手順（再現粒度）**  
提案アルゴリズムは GPF-growth（Generalized Periodic-Frequent pattern-growth）で、(i) GPF-list 作成、(ii) GPF-tree 圧縮、(iii) 条件付き木で再帰採掘、という流れ。citeturn10view0  
論文中の擬似コード（Algorithm 1〜3,6 等）の読み取りから、再現実装に必要な最小骨格は以下。
1) **GPF-list 構築（Algorithm 1）**: DB を走査し item ごとに support S、interesting periods 数 IP、直近出現 timestamp tsl 等を更新し、minSup と minPR×(minSup+1) を用いた剪定で候補 item を得る。citeturn10view0  
2) **GPF-tree 構築（Algorithm 2,3）**: 候補 item 順で各 transaction を挿入し、各ノードが occurrence 情報（timestamps list）を保持するよう拡張する。citeturn10view0  
3) **採掘（本文 5.2 節）**: suffix item ごとに conditional pattern base / conditional tree を作り、各拡張候補について timestamps を集めて periodic-ratio を計算し出力する。citeturn10view0turn11view1  
4) periodic-ratio 計算は getPeriodicRatio（Algorithm 6）として提示され、maxPer を用いて “interesting periods” 比率を算出する。citeturn10view0turn11view1

**E. 計算量（時間・メモリ）**  
本論文上で一般形 O(…) は **未確定**。ただし「FP-tree に基づく従来 pattern-growth は periodic behavior を保持しないので使えず、PF-tree を拡張した GPF-tree が必要」という設計上の理由が説明されている。citeturn10view0

**F. 既存実装の有無、実行方法、ライセンス**  
- 本調査範囲では、SPMF に “GPF-growth（JSS 2017 の partial periodic-frequent patterns）” が実装されている一次情報を確認できていないため **未確定**。citeturn27search2turn30search5  
（※SPMF の periodic pattern mining には PFPM や LPP 系が載っているが、ここでの partial periodic-frequent patterns（periodic-ratio, minPR）そのものの掲載は一次情報として確定できていない、という意味。）citeturn30search5

**G. 再現実装時の落とし穴**  
- **period list の端点**（ts_ini=0, ts_fin=最終 timestamp を含めて period を作る）を誤ると PR(X) が変わり得る。citeturn11view1  
- anti-monotonic property を満たさない（論文が明記）ため、Apriori 的剪定はそのまま適用できない。citeturn9view0turn10view0

**H. このタスク向け適合性**  
パターン同定: 条件付きで適（partial periodic-frequent という“時間的興味”を伴うパターン集合が得られる）。citeturn11view1turn9view0  
区間検出: **直接は不適**（定義・出力は periodic-ratio と support を中心にしており、LPPM のような “time-interval の列挙出力” が仕様として与えられていない）。citeturn11view1turn10view0  
→ 区間が必要なら timestamps（TS_X）からの後処理が必要だが、その「区間の定義・出力仕様」は本論文モデルの外にあるため **未確定（後処理が必要）**。citeturn11view0turn11view1

### LPFIM（Finding Locally and Periodically Frequent Sets…）

**一次情報 URL**
- 原論文（LNCS 3776, 2005）: `https://link.springer.com/content/pdf/10.1007/11590316_91.pdf` citeturn18view0

**A. 問題設定（入力・出力）**  
時間属性付き transaction 群に対して、全期間では minsup に届かないが「ある time interval では頻出」な itemsets（locally frequent sets）を見つけ、各 locally frequent itemset に「頻出な time interval のリスト」を保持する、という問題設定である。citeturn18view0  
出力設計として「各 locally frequent itemset に対し、頻出な time intervals のリストを保持し、各 interval は [start,end] で表す」旨が一次情報に明記されている。citeturn18view0

**B. 厳密な定義（support, interval）**  
- 区間付き support 記法: [t1,t2]Sup(X) を「time interval [t1,t2] における X の support」とする。citeturn18view0  
- 頻出判定: 閾値 σ（%）と tc（区間内 transaction 数）を用いて頻出判定条件を述べている。citeturn18view0  
ただし、同じ段落で「区間内の X 出現数と区間内総 transaction 数の比」と「(σ/100)*tc との比較」が併記され、式の次元（ratio vs count）の読みが一意に定まらないため、**support の厳密解釈は未確定**となる。候補解釈は以下。
- 解釈候補1: [t1,t2]Sup(X) は **count**（区間内で X を含む transaction 数）で、(σ/100)*tc は count 閾値。  
- 解釈候補2: [t1,t2]Sup(X) は **ratio**（count/tc）で、本文の “(σ/100)*tc” は組版上の誤植（本来 σ/100）  
いずれにせよ「区間 [start,end] のリストを itemset に紐づけて保持する」点自体は明確に述べられている。citeturn18view0

**C. パラメータ一覧**  
- σ（min support 相当、% として記述）citeturn18view0  
- τ（confidence、ルール生成に使用）citeturn18view0  
- minthd1: 直近出現からの時間ギャップがこれより小さいなら“同一 time-interval に 포함”、大きいなら新規 interval 開始。citeturn18view0  
- minthd2: 最小 period length（最小 interval 長）。これ未満の短い interval は保持しない（minthd2 を使わないと 1回出ただけでも locally frequent になり得る旨の注意）。citeturn18view0  
推奨範囲・デフォルト: **未確定**（原論文に一般推奨・デフォルトの明記なし）。citeturn18view0

**D. 擬似コードまたは実装手順（再現粒度）**  
原論文は「Apriori を修正」し、各候補 itemset に対して走査中に time-interval を更新する手順を説明する。とくに 1-itemsets の locally frequent 集合 L1 を作る手順として lastseen を保持する説明がある。citeturn18view0  
再現実装（Python）で仕様を落とすなら、少なくとも次を固定する必要がある。
- 候補生成は Apriori の apriorigen(L_{k-1}) を踏襲する。citeturn18view0  
- 各候補 itemset ごとに、走査中に「現在の interval の start」「lastseen」「区間内 support カウンタ」「確定済み interval リスト」を持つ。citeturn18view0  
- lastseen とのギャップが minthd1 を超えたら interval を閉じ、区間内 support が閾値を満たすなら interval リストに追加し、さらに長さが minthd2 以上のみ保持する。citeturn18view0

**E. 計算量（時間・メモリ）**  
一般形 O(…) は **未確定**（原論文に明示なし）。ただし Apriori 系で candidate を保持し、さらに各 candidate ごとに interval リストを保持する設計であるため、出力・中間状態のサイズが性能支配になりやすいことは一次情報の設計記述から読み取れる（ただし定量式は提示されていない）。citeturn18view0

**F. 既存実装の有無、実行方法、ライセンス**  
本調査範囲では、LPFIM（2005）の「公式実装／SPMF 実装」を一次情報として確認できていないため **未確定**。citeturn30search5turn30search2

**G. 再現実装時の落とし穴**  
- support の単位（count vs ratio）が一次情報だけでは一意に取れないため、比較系の仕様として“どちらで実装するか”を固定し、結果解釈に明示する必要がある（前述）。citeturn18view0  
- “ギャップ minthd1” に基づく interval 分割は、タイムスタンプの粒度（秒/日など）に強く依存するため、合成データ生成側と同じ単位系で統一が必須。citeturn18view0turn31view1

**H. このタスク向け適合性**  
パターン同定: 条件付きで可（ローカル頻出を「区間リスト」で伴うため、純粋 FIM と出力型が違う）。citeturn18view0  
区間検出: 適（locally frequent itemset に interval リストを付与する設計が一次情報で明言）。citeturn18view0  

**区間出力の具体例（説明用）**  
原論文が述べるように、各 locally frequent itemset に intervals を紐付けると、例えば  
- itemset {A,B} → intervals = [[t=10,t=40], [t=70,t=90]]  
のような「パターン→区間（複数可）」が出力単位になる（interval は [start,end]）。citeturn18view0

### LPPM（Local Periodic Pattern Mining: LPPM_breadth / LPPM_depth / LPP-Growth）

**一次情報 URL**
- 原論文（Local Periodic Patterns / LPP 定義）: `https://www.philippe-fournier-viger.com/2020_LOCAL_PERIODIC_PATTERNS.pdf` citeturn15view0turn31view2turn32view0  
- 公式ドキュメント（SPMF Local-periodic: LPP-Growth / LPPM_breadth / LPPM_depth）: `https://www.philippe-fournier-viger.com/spmf/Local-periodic.php` citeturn30search1

**A. 問題設定（入力・出力）**  
LPPM は、周期性が全期間で安定とは限らないという前提から、**非事前定義の time-interval(s) において周期的に現れるパターン（LPP）**を見つける問題を定義する。citeturn15view0turn32view0  
出力は「LPP と periodic time-interval(s)」であり、論文中の Table 4 でも LPP と interval の対が例示されている。citeturn16view3turn32view0  
SPMF 文書でも「LPPs and their periodic time-intervals」を出力し、GUI 実行手順と入出力フォーマットを明示している。citeturn30search1turn31view1

**B. 厳密な定義（support, periodicity, interval）**  
この手法は、**transaction ID の gap**ではなく **timestamp 差分の period**をベースに定義する。
- temporal database: transaction Tc と timestamp tsc からなる列で、ts1 ≤ ts2 ≤ … ≤ tsm、同一 timestamp に複数 transaction 可、と明記。citeturn31view1  
- TS_X: itemset X が現れる timestamps の列。citeturn31view2  
- periods per(X): consecutive appearances の timestamp 差分列として  
  per(X) = { ts_{g2}^X − ts_{g1}^X, …, ts_{g_{sup(X)+1}}^X − ts_{g_{sup(X)}}^X }  
  を定義し、|per(X)|=|TS_X|=sup(X) の関係を明示している。citeturn31view2  
- spillover（Definition 7）: surplus（surPer）を累積して soPer を更新し、soPer を 0 以上にクリップする式を与えている（式(1)）。citeturn31view3turn32view0  
- time-interval（Definition 8）: start point から前進スキャンし、soPer が maxSoPer を超えた点を end point として [start,end] を作る。最後まで end が見つからなければ tsmax で閉じる、と定義する。citeturn32view0  
- duration（Definition 9）: dur(X,[tsi,tsj]) = tsj − tsi。dur ≥ minDur の interval を periodic（interesting）とし、X がそのような interval を少なくとも１つ持てば LPP（Definition 10）。citeturn32view0

**C. パラメータ一覧**  
- maxPer: consecutive occurrences 間の期待最大時間（period）に関する閾値。論文例で「maxPer=2 days の意味」を説明している。citeturn16view3turn32view0  
- maxSoPer: spillover（累積超過）許容の上限。strict な max periodicity より柔軟にする目的が説明されている。citeturn16view3turn32view0  
- minDur: interval の最小長。短い interval を捨てる。citeturn16view3turn32view0  
- SPMF 追加パラメータ: timestamps の有無を示す boolean（文書に記載）。citeturn30search1turn31view1  
推奨範囲・デフォルト: **未確定**（一次情報に一般デフォルト値なし）。citeturn30search1turn32view0

**D. 擬似コードまたは実装手順（再現粒度）**  
論文は３アルゴリズム（breadth / depth / growth）を提示し、LPPM_breadth（Algorithm 1）と LPPM_depthSearch（Algorithm 5）、LPP-Growth の骨格（Algorithm 7/9 付近）を示している。citeturn17view1turn17view3turn16view0  
再現実装に必要な最小要素は以下。
- **縦型 ts-list**: 各 itemset の ts-list を保持（bit vector 可）。Apriori-TID/Eclat の縦表現と違い「TID ではなく timestamp を保持する」点が key difference と明記される。citeturn17view0turn31view2  
- **time2interval**: TS_X を走査し、Definition 7–9 に従って periodic time-intervals を構成（soPer を O(1) 更新で判定できる、と説明）。citeturn32view0  
- **LPPM_breadth**: まず 1-itemset の PTL（Periodic Time-interval List）を作り、|PTL|>0 の item を候補 I* に入れて出力。以後は幅優先で ts-list intersection → time2interval → 出力、を繰り返す（Algorithm 1 の概要説明）。citeturn17view0turn17view1  
- **LPPM_depth**: depth-first で ExtensionsOfP を取り、Px と Py の intersection から新 TS を得て time2interval で PTL を計算し、|PTL|>0 のとき出力し再帰する（Algorithm 5）。citeturn17view2  
- **LPP-Growth**: tree-based（FP-tree 拡張）で conditional pattern base を作って再帰出力する、と説明される。citeturn17view3turn16view0

**E. 計算量（時間・メモリ）**  
一次情報として確定できる点は以下。
- soPer の更新と end point 判定は「soPer を O(1) で更新し、soPer>maxSoPer をテストするだけ」で効率的、と説明。citeturn32view0  
一般形の全体 O(…) は **未確定**（ただし出力パターン数・区間数に依存して大きく変わり得ることは論文全体の設計から示唆されるが、固定式は提示されていない）。citeturn15view0turn32view0

**F. 既存実装の有無、実行方法、ライセンス**  
- SPMF に LPP-Growth / LPPM_breadth / LPPM_depth の実装があり、GUI 実行手順（アルゴリズム選択、入力 contextLPP.txt、maxPer/minDur/maxSoPer と timestamps 有無パラメータ設定）が文書化されている。citeturn30search1  
- 入力フォーマット（items … `|` timestamp）も SPMF 文書に明示されている。citeturn30search1  
- ライセンス GNU GPL v3。citeturn6search2turn6search14

**G. 再現実装時の落とし穴（境界条件など）**  
- 同時刻 transaction: 「複数 transaction が同じ timestamp を持てる」と定義にあるため、TS_X と per(X) の生成で “同値 timestamp の差分=0” が起こり得る。これを許容するか（per=0）・どう surPer を定義するかを、Definition 5/7 の式のとおりに実装固定する必要がある。citeturn31view1turn31view2turn32view0  
- 未クローズ interval の扱い: end point が見つからない場合に tsmax で閉じる、と一次情報が明確に規定している（ここを無視すると出力が一致しない）。citeturn32view0  
- 期間定義上、従来の PFP が “最初の gap を g1” とするのに対し、本論文は「空 transaction を足さず、period 数を support と一致させる」方針を明示しており、ここを従来式に寄せると値がズレる。citeturn31view2  
- SPMF 入力前提（重複禁止、ソート、timestamp 付与記法）に合わせたデータ変換が必要。citeturn30search1turn29search3

**H. このタスク向け適合性**  
パターン同定: 目的が “区間付き周期性” なら適、単純頻出とは出力が異なる。citeturn32view0turn15view0  
区間検出: **最適合**（定義と出力が “pattern + periodic time-interval(s)” で、非事前定義区間を直接列挙）。citeturn32view0turn30search1  

**区間をどう出力するか（一次情報ベースの具体例）**  
SPMF 文書および論文例では、LPP と intervals を次のように出す（例：maxPer=3, minDur=7, maxSoPer=2）。citeturn30search1turn16view3  
- {b} → [6thJune 2018, 25thJune 2018]  
- {b,e} → [6thJune 2018, 18thJune 2018]  
など、**1パターンに対して interval が 1個以上（複数可）**である。citeturn16view3turn15view0

## 比較表

以下は、8手法 × A〜H を「比較に必要な仕様観点」に圧縮して並べたもの（詳細は前節の手法別仕様に一次情報付きで記載）。

| 手法 | A 入出力 | B 定義核 | C 主パラメータ | D 実装要点 | E 計算量 | F 既存実装/ライセンス | G 落とし穴 | H 適合性 |
|---|---|---|---|---|---|---|---|---|
| Apriori | DB→frequent itemsets（large itemsets）citeturn20view0turn29search0 | support を用いた反復候補生成citeturn21view1turn20view0 | minsup（+minconf）citeturn20view0 | apriori-gen（join+prune）＋DB多回scanciteturn21view1turn21view3 | 未確定（多回scanは明記）citeturn21view0 | SPMF(GPLv3)citeturn29search0turn6search14 | minsup単位、重複禁止、ソートciteturn29search21turn29search3 | パターン同定◎、区間× |
| FP-Growth | DB→frequent patternsciteturn23view3turn22view0 | support=count、FP-tree/条件木citeturn22view0turn23view2 | minsupciteturn22view0 | FP-tree構築→conditional mining再帰citeturn24view1turn23view3 | FP-treeはDBで上界citeturn24view2 | SPMF(GPLv3)citeturn27search1turn6search14 | 条件木のcount整合、重複禁止citeturn23view3turn29search21 | パターン同定◎、区間× |
| Eclat | DB（縦型）→frequent itemsetsciteturn29search1turn25view0 | tid-listとintersectionでsupportciteturn26view1 | minsupciteturn29search1 | tid-list DFS（class分割は拡張）citeturn26view1turn26view3 | 未確定（tid-list縮小性は言及）citeturn26view1 | SPMF(GPLv3)citeturn29search1turn6search14 | TIDとtimestamp混同禁止citeturn25view0 | パターン同定◎、区間× |
| LCM | DB→frequent/closed/maximal列挙citeturn19view0 | frequency=count、closed/maximal定義citeturn19view0 | support（+各種option）citeturn19view0 | DFS＋conditional DBとメモリ制御citeturn19view0 | 未確定（メモリ安定化説明あり）citeturn19view0 | 公式実装（license未確定）＋SPMF LCMFreq(GPLv3)citeturn19view0turn29search2turn6search14 | 列挙モード不一致（frequent vs closed）citeturn19view0turn29search2 | パターン同定◎、区間× |
| PFPM | DB→periodic frequent itemsetsciteturn14view0turn29search3 | ps(X), min/avg/max periodicityciteturn12view0turn14view0 | minPer/maxPer/minAvg/maxAvgciteturn14view0turn29search3 | Eclat型tid-list探索＋周期指標更新citeturn13view0turn14view2 | 未確定（メモリ比較言及）citeturn13view2 | SPMF(GPLv3)citeturn29search3turn6search14 | minper端点除外など定義厳守citeturn14view0 | 区間×（後処理必要） |
| PPFPM | 時系列DB→partial periodic-frequent patternsciteturn9view0turn11view1 | PR=|IP|/|P|, Pに端点period含むciteturn11view1 | minSup/maxPer/minPRciteturn11view0turn11view1 | GPF-list/GPF-tree→条件木採掘citeturn10view0 | 未確定 | 実装一次情報未確定（SPMF収録確認不可）citeturn30search5turn27search2 | anti-monotonic不成立、端点periodciteturn9view0turn11view1 | 区間×（後処理必要） |
| LPFIM | 時系列DB→locally frequent itemsets＋interval listciteturn18view0 | [t1,t2]Sup(X), interval=[start,end]citeturn18view0 | σ,τ,minthd1,minthd2citeturn18view0 | Apriori改＋lastseenでinterval管理citeturn18view0 | 未確定 | 実装一次情報未確定 | 区間supportの解釈が未確定（候補あり）citeturn18view0 | 区間検出◎（ただし定義解釈要固定） |
| LPPM | 時系列DB→LPP＋periodic time-interval(s)citeturn32view0turn30search1 | per(X), soPer, interval定義, dur≥minDurciteturn31view2turn32view0 | maxPer/maxSoPer/minDur（+timestamps有無）citeturn32view0turn30search1 | ts-list intersection＋time2interval、breadth/depth/growthciteturn17view2turn17view1turn32view0 | soPer更新O(1)明記citeturn32view0 | SPMF(GPLv3)で実行手順/入出力明記citeturn30search1turn6search14 | 同時刻/未クローズinterval等の境界条件citeturn31view1turn32view0 | 区間検出◎（最優先候補） |

## 実装優先順位

比較目的（パターン同定 / 区間検出）に対して「仕様が一次情報で明確」「既存実装で検証しやすい」「Pythonでの再現リスクが低い」順に優先度を提示する。

まず区間検出系は、LPPM が “time-interval をどう定義し、どう閉じ、minDur でどう採択するか”まで定義式と例が揃っており、SPMF に実装・入出力・実行手順が揃うため、最優先で仕様確定・検証が可能である。citeturn32view0turn30search1turn6search14  
LPFIM は “locally frequent itemset に interval list を紐付ける”設計は明確だが、区間 support の式解釈が一意に取れない箇所があり、実装仕様確定に追加の解釈固定が必要となるため、LPPM の後に「比較用ベースライン」として置くのが安全。citeturn18view0turn32view0

パターン同定系は、まず FP-Growth と Eclat（と Apriori ベースライン）で「典型三系統（候補生成型／木型／縦型）」が揃う。FP-Growth は原論文に Algorithm 1/2 があり、SPMF にも実装があるため、再現検証が容易。citeturn23view3turn24view1turn27search1  
LCM は高速系として有力だが、比較対象（frequent vs closed）を固定する必要があるため、比較設計が固まり次第導入するのがよい。SPMF の LCMFreq を使うなら “frequent itemsets” に寄せられる。citeturn19view0turn29search2

PFPM と PPFPM は「周期頻出」比較の追加軸として有用だが、区間を直接出さない（PFPM）／区間出力仕様がモデル外（PPFPM）であり、区間検出比較の主役にはならない。PFPM は SPMF 実装があるため導入は容易だが、PPFPM は実装の一次情報が本調査範囲では確定できていないため、自前実装コストが高い。citeturn29search3turn11view1turn30search5

以上を踏まえた「今すぐ実装すべき手法」優先度は次。

- **最優先（区間検出の比較を成立させる）**: LPPM（LPPM_depth を主、必要なら breadth / growth）citeturn30search1turn32view0  
- **次点（区間検出の対照ベースライン）**: LPFIM（ただし support 解釈を仕様として固定してから）citeturn18view0  
- **パターン同定の中核**: FP-Growth、Eclat、Apriori（ベースライン）citeturn23view3turn29search1turn29search0  
- **性能枠の強化（大規模で必要なら）**: LCM（SPMF LCMFreq または公式実装呼び出し）citeturn29search2turn19view0  
- **追加軸（周期性フィルタとして）**: PFPM（SPMF 実装あり）citeturn29search3turn14view0  
- **保留（一次情報で実装確定しにくい）**: PPFPM（GPF-growth の自前実装前提になりやすい）citeturn10view0turn30search5  

## Python再現実装方針

要件は「Pythonで再現実装するための一次情報収集」だが、同時に「既存実装の有無・実行方法・ライセンス」も評価対象であるため、現実的には **(1) 既存実装で正解（仕様）を固定 → (2) Pythonで同仕様を再現** が最も堅い。

結論として、本タスクに対する妥当案は **「Java/SPMFラッパー＋必要部分のみ自前Python」** のハイブリッドになりやすい。根拠は以下。

- LPPM は定義・例・実装（SPMF）・入出力フォーマットまで一次情報で揃っており、まず SPMF を “参照実装（oracle）” にして合成データ上で出力一致を見ながら Python 実装を詰めるのが最短である。citeturn30search1turn32view0turn6search14  
- PFPM も SPMF に入出力仕様があり、周期指標（#MINPER/#MAXPER/#AVGPER）まで正確に合わせるなら SPMF を基準にできる。citeturn29search3turn14view0  
- 一方、Apriori / FP-Growth / Eclat / LCM は Python で自前実装も可能だが、性能・検証の観点では SPMF を使う方が「同一フォーマット・同一環境で比較」しやすい面がある（ただし GPL 条件を受ける）。citeturn29search0turn27search1turn29search1turn29search2turn6search14  

方針を３案に整理すると次。

- **Java/SPMF ラッパー（推奨：仕様確定フェーズ）**  
  - 長所: LPPM/PFPM など Python 実装が希少な手法でも一次情報どおりに動かせる。入出力フォーマットも文書化されている。citeturn30search1turn29search3  
  - 注意: ライセンスは GNU GPL v3。成果物の配布形態（社内利用/OSS公開/商用）によっては法務確認が必要。citeturn6search14turn6search2  

- **既存Pythonライブラリ呼び出し（部分採用）**  
  - Apriori/FP-Growth だけを Python ライブラリで行い、LPPM/PFPM は SPMF、のような混在は可能。  
  - ただし「言語差による性能比較の歪み」や「support 定義（count/rate）の差」の吸収が必要になるため、本タスクが“出力の比較”中心なら可、“速度比較”中心なら注意が要る。citeturn22view0turn29search0turn29search3turn32view0  

- **自前Python実装（最終的な研究用再現・拡張用途）**  
  - まず LPPM の定義（per/soPer/interval/dur/LPP）を一次情報どおりに実装し、その上で breadth か depth のどちらか一方に絞って再現するのが現実的。citeturn32view0turn17view2  
  - Apriori/FP-Growth/Eclat は原論文擬似コードが揃うため自前実装は可能。citeturn21view1turn23view3turn26view1  
  - LCM の自前再現は公式 README が深い実装論まで踏み込む一方、細部の最適化が多く、純Python再現は難度が高い（ここは“呼び出しで使う”のが妥当になりやすい）。citeturn19view0turn29search2  

## 未確定点と追加確認事項

一次情報に基づき「未確定」と判断した点を列挙する（推論で埋めない）。

LPFIM の区間 support の定義は、本文中で ratio と count 比較が併記されており次元が一意に確定しないため、実装仕様として **どちらを採用するか**を別途決める必要がある（候補2案は前述）。citeturn18view0  

PPFPM（JSS 2017）のアルゴリズム（GPF-growth）について、本調査範囲では SPMF 収録や公式コード公開の一次情報を確定できていないため、比較に組み込むなら **(a) 論文擬似コードから自前実装**、または **(b) 著者提供コードの所在を別途探索して取得**が必要となる。citeturn10view0turn30search5  

LCM 公式実装ページ（lcm.html）からは CLI・出力・設計思想は確定できたが、ライセンス条文の明示は本調査範囲で確認できていないため、配布や組み込みを考える場合は別途ライセンス確認が必要となる。citeturn19view0