# Pending Actions: Paper K (Pharmacoepidemiology)

## PA1: MIMIC-IV Real Data Experiment
- **Priority**: High
- **Description**: Obtain MIMIC-IV access and run experiments on real prescription data
- **Steps**:
  1. Apply for PhysioNet credentialed access
  2. Extract prescription data from `prescriptions` and `pharmacy` tables
  3. Map NDC/drug names to ATC codes using RxNorm/ATC crosswalk
  4. Run E1-E4 on real data
  5. Compare synthetic vs. real data results

## PA2: Real FDA Safety Communication Catalog
- **Priority**: Medium
- **Description**: Compile a catalog of FDA safety communications with dates and targeted drugs
- **Source**: FDA MedWatch archives, FAERS quarterly data files
- **Output**: JSON file with event_id, type, date, targeted_atc, description

## PA3: Seasonal Adjustment
- **Priority**: Medium
- **Description**: Add seasonal decomposition to the support time series before contrast analysis
- **Rationale**: Prescription patterns have seasonal variation (e.g., antibiotics peak in winter)

## PA4: Provider-Level Analysis
- **Priority**: Low
- **Description**: Extend framework to detect provider-level variation in response to safety communications
- **Requires**: Provider identifier in transaction data

## PA5: LaTeX Compilation and Figure Refinement
- **Priority**: Low
- **Description**: Compile manuscript, refine figures for publication quality
- **Steps**: Use latexmk, adjust figure resolution to 300 DPI, add vector graphics
