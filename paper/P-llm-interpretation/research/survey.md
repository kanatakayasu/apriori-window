# Paper P: Literature Survey - LLM for Pattern Interpretation

## Research Gap

既存の頻出パターンマイニング研究はパターンの**検出**に焦点を当てており、
検出結果の**解釈**はドメイン専門家に委ねられている。
LLM を用いたデータマイニング結果の自動解釈は新しい研究方向である。

## Key References

### 頻出パターンマイニング
1. Agrawal & Srikant (1994) - Apriori algorithm
2. Han et al. (2000) - FP-Growth
3. Mannila et al. (1997) - Episode mining
4. Webb (2007) - Significant patterns

### LLM for Data Analysis
5. Brown et al. (2020) - GPT-3, few-shot learning
6. Wei et al. (2022) - Chain-of-Thought prompting
7. OpenAI (2023) - GPT-4
8. Zhang et al. (2024) - LLM for Data Mining survey
9. Touvron et al. (2023) - LLaMA

### Text Generation & Summarization
10. Narayan et al. (2018) - Extreme summarization
11. Liu et al. (2023) - ChatGPT survey

## Positioning

| 手法 | パターン検出 | 自動解釈 | 時間的分析 |
|------|:---:|:---:|:---:|
| Apriori | Y | N | N |
| Dense Interval Mining | Y | N | Y |
| LLM for DM (survey) | N | Y | N |
| **本研究** | **Y** | **Y** | **Y** |
