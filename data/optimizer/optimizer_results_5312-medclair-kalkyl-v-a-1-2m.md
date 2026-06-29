# Optimizer Results

- Input file: `data/normalized/canonical_normalized_models.json`
- Selected formula: `thousands_rounded_path`
- Search method: bounded_beam_search
- Search details: bounded=True, approximate=True, global_optimality_guaranteed=False
- Campaign count: 1
- Options generated: 6
- Strategy: `math`
- Allow negative: `False`
- Beam width: 300
- Allowed profile sizes: 15000, 35000, 75000, 125000, 175000
- Warnings: none

## Executive Summary

| Workbook | Sheet | Recommended Option | Recommended Diff | Baseline Diff | Improvement vs Baseline | Main Note |
|---|---|---|---:|---:|---:|---|
| 5312 Medclair Kalkyl (V.A).xlsx | 1.2M | best_strategic_fit | 207.375 | 207.375 | 0 | Recommended as best balance between diff fit and distribution. |

## Sheet: 5312 Medclair Kalkyl (V.A).xlsx / 1.2M

### Recommendation
Recommended as best balance between diff fit and distribution.

### Budget Breakdown
- Total budget: 1200000
- Agency fee: 448965
- Paid media: 220000
- Paid media included in target: yes
- Profile fee deduction / extra agency fee: 7.5%
- Available profile-fee target: 491207.375

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_strategic_fit | 1 | 207.375 | 491000 | 11 | 2 | 520 | 0 | no | Balanced tier distribution. |
| current_workbook_mix | 2 | 207.375 | 491000 | 9 | 1 | 520 | 1 | no | Highly concentrated tier mix |
| larger_profile_alternative | 3 | 1207.375 | 490000 | 11 | 3 | 560 | 0 | no | Balanced tier distribution. |
| best_mathematical_fit | 4 | 207.375 | 491000 | 15 | 2 | 520 | 1 | no | Highly concentrated tier mix |
| fallback_option | 5 | 207.375 | 491000 | 13 | 2 | 520 | 1 | no | Highly concentrated tier mix |
| balanced_option | 6 | 5707.375 | 485500 | 11 | 2 | 515 | 0 | no | Balanced tier distribution. |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B20 | 15000 | 15000 | TikTok | UK | 800 | 1 | 8000 |
| B21 | 15000 | 15000 | TikTok | UK | 800 | 1 | 8000 |
| B22 | 15000 | 15000 | TikTok | UK | 800 | 1 | 8000 |
| B23 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B24 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B25 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B26 | 15000 | 15000 | Instagram | UK | 800 | 1 | 8000 |
| B27 | 15000 | 15000 | Instagram | UK | 800 | 1 | 8000 |
| B28 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B29 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B30 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B31 | 75000 | 75000 | Instagram | UK | 800 | 1 | 44000 |
| B32 | 15000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B33 | 15000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B34 | 15000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B35 | 15000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B36 | 35000 | 35000 | TikTok | US | 1100 | 1 | 33000 |
| B37 | 35000 | 35000 | TikTok | US | 1100 | 1 | 33000 |
| B38 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B39 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B40 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B41 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B42 | 35000 | 75000 | Instagram | US | 1100 | 1 | 60500 |
| B43 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |

### Other Options
- current_workbook_mix: diff=207.375, warnings=1, note=Highly concentrated tier mix
- larger_profile_alternative: diff=1207.375, warnings=0, note=Balanced tier distribution.
- best_mathematical_fit: diff=207.375, warnings=1, note=Highly concentrated tier mix
- fallback_option: diff=207.375, warnings=1, note=Highly concentrated tier mix
- balanced_option: diff=5707.375, warnings=0, note=Balanced tier distribution.

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Allowed profile sizes: 15000, 35000, 75000, 125000, 175000
- Beam width: 300; expanded=27810; retained=300
- Baseline comparison for best mathematical fit: equals
- Recommended differs from best mathematical fit: yes
- Strategic warnings: current_workbook_mix: Highly concentrated tier mix; best_mathematical_fit: Highly concentrated tier mix; fallback_option: Highly concentrated tier mix
- Result warnings: none
