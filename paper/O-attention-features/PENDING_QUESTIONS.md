# Pending Questions — Paper O (Attention Features)

## Open Questions

1. **PyTorch Implementation**: The current NumPy-based gradient approach achieves limited convergence. Should we require PyTorch as a dependency for production experiments, or keep the NumPy fallback as the primary implementation?

2. **Event Feature Richness**: Currently events are encoded with only 3 features (normalized timestamp, magnitude, type hash). Would categorical embeddings or text-based event descriptions significantly improve attribution accuracy?

3. **Real-World Validation**: The experiments use synthetic data only. Which real-world datasets with known event-pattern ground truth should be prioritized? Dunnhumby campaign data is a candidate but lacks explicit event-pattern ground truth labels.

4. **Attention as Explanation**: Given the debate in NLP literature (Jain & Wallace 2019 vs. Wiegreffe & Pinter 2019), how strongly should we claim attention weights are "explanations" vs. "indicators"? Current results show near-uniform attention, which weakens the interpretability argument.

5. **Multi-Layer Architecture**: Would stacking multiple cross-attention layers improve attribution? The current single-layer design may not capture complex event-pattern relationships.

6. **Venue Fit**: Is KDD/CIKM the right venue, or would a workshop on interpretable ML or temporal data mining be more appropriate given the current accuracy levels?
