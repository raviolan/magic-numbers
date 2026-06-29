# Optimizer Results

- Input file: `data/normalized/canonical_normalized_models.json`
- Selected formula: `thousands_rounded_path`
- Search method: bounded beam search
- Search guarantee: bounded/approximate only; global optimality is not guaranteed
- Campaign count: 1
- Options generated: 6
- Strategy: `math`
- Allow negative: `False`
- Beam width: 1000
- Warnings: none

## Executive Summary

| Workbook | Sheet | Recommended Option | Recommended Diff | Baseline Diff | Improvement vs Baseline | Main Note |
|---|---|---|---:|---:|---:|---|
| 5311 Dear Dahlia Kalkyl (V.A).xlsx | 10 profiler | fallback_option | 13.8 | -46.2 | 32.4 | Recommended as best balance between budget fit and profile quality. |

## Sheet: 5311 Dear Dahlia Kalkyl (V.A).xlsx / 10 profiler

### Recommendation
Recommended as best balance between budget fit and profile quality.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| fallback_option | 1 | 13.8 | 15800 | 3 | 5 | 365 | 0 | yes | Majority of rows are 75K+ tiers. |
| balanced_option | 2 | 93.8 | 15720 | 3 | 4 | 380 | 0 | no | More balanced mid-tier distribution |
| best_mathematical_fit | 3 | 3.8 | 15810 | 4 | 2 | 370 | 1 | yes | Very high 15K share |
| best_strategic_fit | 4 | 673.8 | 15140 | 0 | 3 | 365 | 0 | no | No 15K profiles used. |
| larger_profile_alternative | 5 | 1333.8 | 14480 | 0 | 3 | 365 | 0 | no | No 15K profiles used. |
| current_workbook_mix | 6 | -46.2 | 15860 | 0 | 4 | 395 | 0 | no | No 15K profiles used. |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B9 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B10 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B11 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B12 | 75000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B13 | 75000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B14 | 35000 | 75000 | Instagram | null | 46 | 1 | 2530 |
| B15 | 35000 | 75000 | Instagram | null | 46 | 1 | 2530 |
| B16 | 35000 | 75000 | Instagram | null | 46 | 1 | 2530 |
| B17 | 75000 | 75000 | Instagram | null | 46 | 1 | 2530 |
| B18 | 75000 | 75000 | Instagram | null | 46 | 1 | 2530 |

### Other Options
- balanced_option: diff=93.8, warnings=0, note=More balanced mid-tier distribution
- best_mathematical_fit: diff=3.8, warnings=1, note=Very high 15K share
- best_strategic_fit: diff=673.8, warnings=0, note=No 15K profiles used.
- larger_profile_alternative: diff=1333.8, warnings=0, note=No 15K profiles used.
- current_workbook_mix: diff=-46.2, warnings=0, note=No 15K profiles used.

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=15455; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: yes
- Strategic warnings: best_mathematical_fit: Very high 15K share
- Result warnings: none
