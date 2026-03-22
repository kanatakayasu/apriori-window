# PENDING_QUESTIONS — Paper F (MDL Summary)

## 未解決質問

1. **StreamKrimp の公式実装の可用性**: StreamKrimp のオリジナル実装は公開されていない可能性がある。再実装が必要か、代替ベースラインで十分か？
   - 暫定方針: KRIMP のバッチ分割版で近似する

2. **密集区間の最大長制約**: MDL 符号化において密集区間の最大長に制約を設けるべきか？
   - 暫定方針: 制約なしで開始し、圧縮率が改善しない場合にプルーニングを導入

3. **符号長計算の実数精度**: prequential code length で log2 を多用するが、浮動小数点精度で十分か？
   - 暫定方針: Python float64 で進め、問題が生じたら mpmath を検討

4. **KDD vs ECML-PKDD のページ制限**: 投稿先によって実験セクションの深さが変わる
   - 暫定方針: KDD フルペーパー (9p + refs) を想定して執筆
