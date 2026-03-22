# Literature Review: Dense Prescription Patterns and Regulatory Event Attribution in Pharmacoepidemiology

## 1. Pharmacoepidemiology Methods

### 1.1 Self-Controlled Case Series (SCCS)
- **Whitaker et al. (2006)**: Foundational methodology paper for SCCS, using only cases to evaluate transient exposure-acute event associations. Controls for all time-stable confounders via within-person comparisons.
- **Cadarette & Kim (2021)**: ISPE-endorsed guidance on self-controlled study designs. SCCS best suited for transient exposures and abrupt outcomes.
- **Petersen et al. (2016)**: Systematic review of self-controlled designs in pharmacoepidemiology using electronic healthcare databases. Identifies increasing adoption in drug safety studies.

### 1.2 Interrupted Time Series (ITS)
- **Bernal et al. (2017)**: Tutorial on interrupted time series regression for public health intervention evaluation. Segmented regression most common method (67%).
- **Jandoc et al. (2015)**: Systematic review showing ITS use in drug utilization research is increasing; 18% of studies examine safety advisories.
- **Wagner et al. (2002)**: Segmented regression analysis of ITS studies in drug utilization research. Quasi-experimental gold standard when RCTs infeasible.

### 1.3 Cohort and Case-Control Studies
- Traditional designs for pharmacovigilance but subject to confounding; self-controlled designs increasingly preferred.

## 2. Prescription Pattern Mining

### 2.1 Association Rule Mining in Pharmacy
- **Carvalho et al. (2022)**: Apriori algorithm applied to identify polypharmacy patterns in metformin users—drug combinations up to 7 drugs. Directly relevant to our dense itemset approach.
- **Pappa et al. (2017)**: Association Rule and Frequent-Set analysis for concomitant medication use evaluation in older adults with geriatric syndromes.
- **Patel et al. (2024)**: Data mining approach for polypharmacy and DDI detection in diabetes medications using ARM techniques.

### 2.2 Sequential Pattern Mining
- **Wright et al. (2015)**: CSPADE algorithm for mining sequential prescription patterns at drug class and generic drug levels, ranked by support.
- **Batal et al. (2012)**: Temporal pattern mining approach for classifying EHR data; addresses challenge of low minimum support in healthcare data.

### 2.3 Temporal Pattern Discovery (TPD)
- **Zorych et al. (2013)**: TPD method for adverse drug event signal detection using electronic healthcare databases; based on Information Component (IC) disproportionality measure.
- **Noren et al. (2010)**: Temporal pattern discovery in longitudinal electronic patient records; graphical statistical approach for temporal drug-outcome associations.

### 2.4 Topic Models and Neural Approaches
- **Chen et al. (2017)**: Topic model for identifying prescription patterns from diseases and medications data.
- **Steinberg et al. (2022)**: Representation learning for medication codes in MIMIC-IV using GloVe embeddings.

## 3. Pharmacovigilance Signal Detection

### 3.1 Disproportionality Analysis
- **Evans et al. (2001)**: Proportional Reporting Ratio (PRR)—compares proportion of target drug-AE combination vs. other drug-AE combinations.
- **Rothman et al. (2004)**: Reporting Odds Ratio (ROR)—odds ratio for particular AE in specific drug vs. other drugs. Higher sensitivity than PRR.
- **Bate et al. (1998)**: Bayesian Confidence Propagation Neural Network (BCPNN)—Information Component as Bayesian disproportionality measure.
- **DuMouchel (1999)**: Gamma-Poisson Shrinker (GPS/MGPS)—Bayesian shrinkage for rare event detection.

### 3.2 Comparative Studies
- **Lee et al. (2020)**: Comparison of data mining methods for ADR signal detection with hierarchical structure. LRT, GPS, BCPNN more conservative than ROR, PRR.
- **Ang et al. (2016)**: Comparison of three disproportionality measures in Singapore spontaneous ADR reporting data.

### 3.3 Machine Learning Approaches
- **Li et al. (2025)**: LSTM model for adverse drug reaction signal detection—temporal deep learning approach.
- **Fusaroli et al. (2021)**: Combining pharmacological network model with Bayesian signal detection.

## 4. FDA Safety Communications Impact

### 4.1 Impact Assessment Studies
- **Dusetzina et al. (2012)**: Systematic review of FDA drug risk communication impact on healthcare utilization. 40 studies assessed targeted drug use changes; many communications showed delayed or no impact.
- **Marcum et al. (2012)**: Narrative review of FDA Drug Safety Communications with clinical considerations for older adults.

### 4.2 Regulatory Actions
- **Onakpoya et al. (2019)**: Pharmacovigilance perspective on drug withdrawals, data mining, and policy implications. Pharmacovigilance backbone for drug safety interventions including withdrawals and labelling changes.

## 5. Clinical Data Mining with EHR/Claims

### 5.1 MIMIC-IV Studies
- **Johnson et al. (2023)**: MIMIC-IV freely accessible EHR dataset from Beth Israel Deaconess Medical Center. Includes prescriptions, pharmacy, eMAR tables.
- **Gupta et al. (2022)**: Extensive data processing pipeline for MIMIC-IV, including medication data standardization.

### 5.2 EHR Mining Methods
- **Jensen et al. (2012)**: Comprehensive survey of mining electronic health records.
- **Landi et al. (2020)**: Temporal condition pattern mining in large, sparse EHR data; case study in pediatric asthma.
- **Alonso Moral et al. (2023)**: Acquisition of temporal patterns from EHR for multimorbid patients.

### 5.3 Prescription Sequence Symmetry Analysis (PSSA)
- **Hallas (1996)**: Original PSSA method for ADR signal detection using temporal symmetry of prescriptions.
- **Pratt et al. (2015)**: Multi-country assessment of PSSA for consistent ADR detection across datasets.

## 6. Gap Identification

### 6.1 What Exists
1. Disproportionality methods (PRR, ROR, BCPNN) for cross-sectional signal detection
2. SCCS/ITS for individual-level or aggregate temporal associations
3. Association rule mining for static co-prescription patterns
4. Sequential pattern mining for ordered medication sequences
5. TPD for temporal drug-outcome visualization

### 6.2 What Is Missing
1. **Dense interval detection for prescription patterns**: No existing method identifies time periods where specific drug co-prescription patterns become unusually frequent (dense).
2. **Automated regulatory event attribution**: Current ITS studies manually specify intervention points; no automated method links detected pattern changes to external regulatory events.
3. **Multi-pattern contrast analysis**: Existing methods analyze one drug at a time; no framework systematically detects which co-prescription patterns appear or disappear around regulatory events.
4. **Sliding window approach for prescription support time series**: Standard pharmacovigilance uses fixed time bins; sliding windows provide finer temporal resolution.

### 6.3 Our Contribution
We bridge frequent itemset mining and pharmacovigilance by:
1. Adapting dense interval detection (apriori_window) to prescription transaction data
2. Formalizing regulatory event attribution as a contrast pattern problem
3. Providing automated detection of prescription pattern changes around FDA safety communications
4. Demonstrating the approach on synthetic MIMIC-IV-style prescription data
