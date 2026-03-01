## 実験対象データ

### 公開データセット候補

| データセット | 期間 | タイムスタンプ | バスケット構造 | イベント情報 | 適合度 |
|---|---|---|---|---|---|
| **Dunnhumby Complete Journey** | 2年（週単位） | 週番号+日番号 | ◎ `basket_id` 付き | ◎ クーポン・プロモーション情報あり | **◎** |
| **UCI Online Retail II** | 2年 | 分単位 | ○ `InvoiceNo` 単位 | なし | **◎** |
| **IJCAI-15 Tmall** | 6ヶ月 | 日単位 | ○ 推定可 | ○ Double 11（独身の日セール） | **○** |
| **H&M Fashion** | 2年 | 日単位 | △ 顧客+日で代替 | なし | **○** |
| **Olist Brazilian EC** | 2年 | 秒単位 | ○ `order_id` 単位 | なし | **○** |
| **Ta-Feng Grocery** | 4ヶ月 | 日単位 | ○ | なし | **○** |
| **Instacart 2017** | 不明 | 曜日+時刻帯のみ | ◎ | なし | **△** 絶対日付なし |

#### 推奨

1. **Dunnhumby Complete Journey**（第1推奨）
   - `basket_id` によるバスケット構造、2年間の週次データ、プロモーション情報を全て備える
   - 課題②のイベント関連付け検証に直接使える唯一のデータセット
   - https://www.dunnhumby.com/source-files/ （無料・要登録）

2. **UCI Online Retail II**（第2推奨・まず試すならこれ）
   - 登録不要・即ダウンロード可（CC BY 4.0）
   - InvoiceNo 単位のバスケット構造・分単位タイムスタンプ・2年間・約100万行
   - 論文引用実績多数で再現性確認が容易
   - https://archive.uci.edu/dataset/502/online+retail+ii

3. **IJCAI-15 Tmall**（イベント分析を重視する場合）
   - Double 11（11月11日）という大規模外部イベント前後のデータが含まれる
   - https://tianchi.aliyun.com/dataset/42 （Alibaba アカウント要登録）

### その他
- 擬似データセット（動作確認・単体テスト用）
- 澪標のECサイトデータセット（最終的な有用性検証）