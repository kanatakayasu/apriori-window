# Pending Questions: Paper K (Pharmacoepidemiology)

## Q1: MIMIC-IV Data Access
- Can we obtain MIMIC-IV credentialed access for real prescription data validation?
- If yes, which tables are needed? (prescriptions, pharmacy, emar)
- Timeline for data access approval?

## Q2: ATC Level Selection
- Currently using ATC level 3 (pharmacological subgroup). Should we also run experiments at level 4 (chemical subgroup) for finer granularity?
- Trade-off: more specific patterns vs. sparser data

## Q3: Real FDA Safety Communications
- Should we compile a ground-truth list of FDA safety communications with known prescription impact for validation?
- Suggested sources: FDA MedWatch, FDA FAERS

## Q4: Causal Inference Extension
- Should we add a difference-in-differences or synthetic control analysis as an additional validation layer?
- This would strengthen causal claims but increases complexity

## Q5: Target Venue Preference
- JAMIA (full paper, ~10 pages) vs. AMIA Annual Symposium (short paper, ~6 pages)?
- Current manuscript is structured for JAMIA full paper format
