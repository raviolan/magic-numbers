# Optimizer Results

- Input file: `data/normalized/canonical_normalized_models.json`
- Selected formula: `thousands_rounded_path`
- Search method: bounded beam search
- Search guarantee: bounded/approximate only; global optimality is not guaranteed
- Campaign count: 6
- Options generated: 36
- Strategy: `math`
- Allow negative: `False`
- Beam width: 1000
- Warnings: none

## Executive Summary

| Workbook | Sheet | Recommended Option | Recommended Diff | Baseline Diff | Improvement vs Baseline | Main Note |
|---|---|---|---:|---:|---:|---|
| 5311 Dear Dahlia Kalkyl (V.A).xlsx | 10 profiler | best_mathematical_fit | 3.8 | -46.2 | 42.4 | Closest mathematical fit. |
| 5311 Dear Dahlia Kalkyl (V.A).xlsx | 20 profiler | best_mathematical_fit | 4.8 | 114.8 | 110 | Closest mathematical fit. |
| 5311 Dear Dahlia Kalkyl (V.A).xlsx | 30 profiler | balanced_option | 450.8 | 480.8 | 30 | Recommended as best balance between diff fit and distribution. |
| 5312 Medclair Kalkyl (V.A).xlsx | 600K | best_mathematical_fit | 140.375 | 1640.375 | 1500 | Closest mathematical fit. |
| 5312 Medclair Kalkyl (V.A).xlsx | 1.2M | best_strategic_fit | 207.375 | 207.375 | 0 | Recommended as best balance between diff fit and distribution. |
| 5312 Medclair Kalkyl (V.A).xlsx | 2M | best_strategic_fit | 2100.5 | 13100.5 | 11000 | Recommended as best balance between diff fit and distribution. |

## Sheet: 5311 Dear Dahlia Kalkyl (V.A).xlsx / 10 profiler

### Recommendation
Closest mathematical fit.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_mathematical_fit | 1 | 3.8 | 15810 | 4 | 2 | 370 | 0 | yes | Uses a broad mix of tiers. |
| fallback_option | 2 | 13.8 | 15800 | 3 | 5 | 365 | 1 | yes | Highly concentrated tier mix |
| best_strategic_fit | 3 | 93.8 | 15720 | 3 | 4 | 380 | 0 | no | Uses a broad mix of tiers. |
| balanced_option | 4 | 223.8 | 15590 | 4 | 3 | 425 | 0 | no | Uses a broad mix of tiers. |
| larger_profile_alternative | 5 | 1293.8 | 14520 | 3 | 4 | 385 | 0 | no | Uses a broad mix of tiers. |
| current_workbook_mix | 6 | -46.2 | 15860 | 0 | 4 | 395 | 1 | no | Highly concentrated tier mix |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B9 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B10 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B11 | 35000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B12 | 75000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B13 | 75000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B14 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B15 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B16 | 35000 | 125000 | Instagram | null | 46 | 1 | 4140 |
| B17 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B18 | 75000 | 175000 | Instagram | null | 46 | 1 | 5750 |

### Other Options
- fallback_option: diff=13.8, warnings=1, note=Highly concentrated tier mix
- best_strategic_fit: diff=93.8, warnings=0, note=Uses a broad mix of tiers.
- balanced_option: diff=223.8, warnings=0, note=Uses a broad mix of tiers.
- larger_profile_alternative: diff=1293.8, warnings=0, note=Uses a broad mix of tiers.
- current_workbook_mix: diff=-46.2, warnings=1, note=Highly concentrated tier mix

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=15455; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: no
- Strategic warnings: fallback_option: Highly concentrated tier mix; current_workbook_mix: Highly concentrated tier mix
- Result warnings: none

## Sheet: 5311 Dear Dahlia Kalkyl (V.A).xlsx / 20 profiler

### Recommendation
Closest mathematical fit.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_mathematical_fit | 1 | 4.8 | 31830 | 9 | 7 | 845 | 0 | yes | Uses a broad mix of tiers. |
| fallback_option | 2 | 4.8 | 31830 | 9 | 7 | 845 | 0 | yes | Uses a broad mix of tiers. |
| larger_profile_alternative | 3 | 4.8 | 31830 | 6 | 9 | 845 | 0 | yes | Uses a broad mix of tiers. |
| balanced_option | 4 | 174.8 | 31660 | 6 | 8 | 815 | 0 | no | Uses a broad mix of tiers. |
| best_strategic_fit | 5 | 194.8 | 31640 | 6 | 8 | 805 | 0 | no | Uses a broad mix of tiers. |
| current_workbook_mix | 6 | 114.8 | 31720 | 0 | 8 | 790 | 1 | no | Highly concentrated tier mix |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B9 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B10 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B11 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B12 | 35000 | 15000 | TikTok | null | 35 | 1 | 350 |
| B13 | 35000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B14 | 35000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B15 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B16 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B17 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B18 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B19 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B20 | 35000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B21 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B22 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B23 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B24 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B25 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B26 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B27 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B28 | 75000 | 75000 | Instagram | null | 46 | 1 | 2530 |

### Other Options
- fallback_option: diff=4.8, warnings=0, note=Uses a broad mix of tiers.
- larger_profile_alternative: diff=4.8, warnings=0, note=Uses a broad mix of tiers.
- balanced_option: diff=174.8, warnings=0, note=Uses a broad mix of tiers.
- best_strategic_fit: diff=194.8, warnings=0, note=Uses a broad mix of tiers.
- current_workbook_mix: diff=114.8, warnings=1, note=Highly concentrated tier mix

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=60010; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: no
- Strategic warnings: current_workbook_mix: Highly concentrated tier mix
- Result warnings: none

## Sheet: 5311 Dear Dahlia Kalkyl (V.A).xlsx / 30 profiler

### Recommendation
Recommended as best balance between diff fit and distribution.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| balanced_option | 1 | 450.8 | 48330 | 9 | 12 | 1285 | 0 | yes | Uses a broad mix of tiers. |
| best_strategic_fit | 2 | 450.8 | 48330 | 9 | 12 | 1285 | 0 | yes | Uses a broad mix of tiers. |
| larger_profile_alternative | 3 | 450.8 | 48330 | 9 | 12 | 1285 | 0 | yes | Uses a broad mix of tiers. |
| best_mathematical_fit | 4 | 20.8 | 48760 | 0 | 11 | 1225 | 1 | yes | Highly concentrated tier mix |
| fallback_option | 5 | 20.8 | 48760 | 0 | 11 | 1225 | 1 | yes | Highly concentrated tier mix |
| current_workbook_mix | 6 | 480.8 | 48300 | 0 | 13 | 1215 | 1 | no | Highly concentrated tier mix |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B9 | 35000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B10 | 35000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B11 | 35000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B12 | 35000 | 35000 | TikTok | null | 35 | 1 | 1050 |
| B13 | 35000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B14 | 35000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B15 | 35000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B16 | 75000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B17 | 75000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B18 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B19 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B20 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B21 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B22 | 75000 | 125000 | TikTok | null | 35 | 1 | 3500 |
| B23 | 75000 | 75000 | TikTok | null | 35 | 1 | 2100 |
| B24 | 35000 | 125000 | Instagram | null | 46 | 1 | 4140 |
| B25 | 35000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B26 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B27 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B28 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B29 | 35000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B30 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B31 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B32 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B33 | 35000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B34 | 75000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B35 | 75000 | 15000 | Instagram | null | 46 | 1 | 460 |
| B36 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B37 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |
| B38 | 75000 | 35000 | Instagram | null | 46 | 1 | 1150 |

### Other Options
- best_strategic_fit: diff=450.8, warnings=0, note=Uses a broad mix of tiers.
- larger_profile_alternative: diff=450.8, warnings=0, note=Uses a broad mix of tiers.
- best_mathematical_fit: diff=20.8, warnings=1, note=Highly concentrated tier mix
- fallback_option: diff=20.8, warnings=1, note=Highly concentrated tier mix
- current_workbook_mix: diff=480.8, warnings=1, note=Highly concentrated tier mix

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=110010; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: yes
- Strategic warnings: best_mathematical_fit: Highly concentrated tier mix; fallback_option: Highly concentrated tier mix; current_workbook_mix: Highly concentrated tier mix
- Result warnings: none

## Sheet: 5312 Medclair Kalkyl (V.A).xlsx / 600K

### Recommendation
Closest mathematical fit.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_mathematical_fit | 1 | 140.375 | 206500 | 7 | 0 | 215 | 1 | yes | Highly concentrated tier mix |
| fallback_option | 2 | 640.375 | 206000 | 11 | 1 | 235 | 2 | yes | Highly concentrated tier mix |
| best_strategic_fit | 3 | 1640.375 | 205000 | 6 | 0 | 215 | 1 | no | Highly concentrated tier mix |
| current_workbook_mix | 4 | 1640.375 | 205000 | 6 | 0 | 215 | 1 | no | Highly concentrated tier mix |
| larger_profile_alternative | 5 | 4140.375 | 202500 | 6 | 0 | 225 | 1 | no | Highly concentrated tier mix |
| balanced_option | 6 | 7140.375 | 199500 | 6 | 0 | 210 | 1 | no | Highly concentrated tier mix |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B20 | 15000 | 15000 | TikTok | UK | 800 | 1 | 8000 |
| B21 | 15000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B22 | 15000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B23 | 35000 | 15000 | Instagram | UK | 800 | 1 | 8000 |
| B24 | 35000 | 15000 | Instagram | UK | 800 | 1 | 8000 |
| B25 | 35000 | 15000 | Instagram | UK | 800 | 1 | 8000 |
| B26 | 15000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B27 | 15000 | 35000 | TikTok | US | 1100 | 1 | 33000 |
| B28 | 35000 | 35000 | TikTok | US | 1100 | 1 | 33000 |
| B29 | 15000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B30 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B31 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |

### Other Options
- fallback_option: diff=640.375, warnings=2, note=Highly concentrated tier mix
- best_strategic_fit: diff=1640.375, warnings=1, note=Highly concentrated tier mix
- current_workbook_mix: diff=1640.375, warnings=1, note=Highly concentrated tier mix
- larger_profile_alternative: diff=4140.375, warnings=1, note=Highly concentrated tier mix
- balanced_option: diff=7140.375, warnings=1, note=Highly concentrated tier mix

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=31500; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: no
- Strategic warnings: best_mathematical_fit: Highly concentrated tier mix; fallback_option: Highly concentrated tier mix; fallback_option: Low mid-tier representation; best_strategic_fit: Highly concentrated tier mix; current_workbook_mix: Highly concentrated tier mix; larger_profile_alternative: Highly concentrated tier mix; balanced_option: Highly concentrated tier mix
- Result warnings: none

## Sheet: 5312 Medclair Kalkyl (V.A).xlsx / 1.2M

### Recommendation
Recommended as best balance between diff fit and distribution.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_strategic_fit | 1 | 207.375 | 491000 | 11 | 2 | 520 | 0 | no | Balanced tier distribution. |
| current_workbook_mix | 2 | 207.375 | 491000 | 9 | 1 | 520 | 1 | no | Highly concentrated tier mix |
| larger_profile_alternative | 3 | 1207.375 | 490000 | 11 | 3 | 560 | 0 | no | Balanced tier distribution. |
| best_mathematical_fit | 4 | 207.375 | 491000 | 19 | 3 | 550 | 2 | no | Highly concentrated tier mix |
| fallback_option | 5 | 207.375 | 491000 | 17 | 3 | 550 | 1 | no | Highly concentrated tier mix |
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
| B39 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B40 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B41 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B42 | 35000 | 35000 | Instagram | US | 1100 | 1 | 27500 |
| B43 | 35000 | 75000 | Instagram | US | 1100 | 1 | 60500 |

### Other Options
- current_workbook_mix: diff=207.375, warnings=1, note=Highly concentrated tier mix
- larger_profile_alternative: diff=1207.375, warnings=0, note=Balanced tier distribution.
- best_mathematical_fit: diff=207.375, warnings=2, note=Highly concentrated tier mix
- fallback_option: diff=207.375, warnings=1, note=Highly concentrated tier mix
- balanced_option: diff=5707.375, warnings=0, note=Balanced tier distribution.

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=86430; retained=1000
- Baseline comparison for best mathematical fit: equals
- Recommended differs from best mathematical fit: yes
- Strategic warnings: current_workbook_mix: Highly concentrated tier mix; best_mathematical_fit: Highly concentrated tier mix; best_mathematical_fit: Low mid-tier representation; fallback_option: Highly concentrated tier mix
- Result warnings: none

## Sheet: 5312 Medclair Kalkyl (V.A).xlsx / 2M

### Recommendation
Recommended as best balance between diff fit and distribution.

### Option Comparison
| Option | Rec Rank | Diff | Fee Sum | 15K Count | 75K+ Count | Total Impressions | Warning Count | Improves Baseline | Main Note |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| best_strategic_fit | 1 | 2100.5 | 926618 | 9 | 7 | 985 | 0 | yes | Uses a broad mix of tiers. |
| larger_profile_alternative | 2 | 2100.5 | 926618 | 10 | 6 | 985 | 0 | yes | Uses a broad mix of tiers. |
| best_mathematical_fit | 3 | 100.5 | 928618 | 18 | 10 | 1100 | 1 | yes | Highly concentrated tier mix |
| fallback_option | 4 | 100.5 | 928618 | 19 | 8 | 1100 | 1 | yes | Highly concentrated tier mix |
| balanced_option | 5 | 7600.5 | 921118 | 10 | 6 | 980 | 0 | yes | Uses a broad mix of tiers. |
| current_workbook_mix | 6 | 13100.5 | 915618 | 3 | 4 | 975 | 1 | no | Highly concentrated tier mix |

### Fill Instructions for Recommended Option
| Cell | Previous Size | Recommended Size | Channel | Market | CPM | Activations | Row Fee |
|---|---:|---:|---|---|---:|---:|---:|
| B20 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B21 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B22 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B23 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B24 | 35000 | 35000 | TikTok | UK | 800 | 1 | 24000 |
| B25 | 75000 | 75000 | TikTok | UK | 685.3 | 1 | 41118 |
| B26 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B27 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B28 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B29 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B30 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B31 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B32 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B33 | 35000 | 35000 | Instagram | UK | 800 | 1 | 20000 |
| B34 | 125000 | 125000 | Instagram | UK | 800 | 1 | 72000 |
| B35 | 35000 | 35000 | TikTok | US | 1100 | 1 | 33000 |
| B36 | 35000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B37 | 35000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B38 | 35000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B39 | 35000 | 15000 | TikTok | US | 1100 | 1 | 11000 |
| B40 | 35000 | 75000 | TikTok | US | 1100 | 1 | 66000 |
| B41 | 35000 | 75000 | TikTok | US | 1100 | 1 | 66000 |
| B42 | 75000 | 75000 | TikTok | US | 1100 | 1 | 66000 |
| B43 | 125000 | 75000 | TikTok | US | 1100 | 1 | 66000 |
| B44 | 15000 | 175000 | Instagram | US | 1100 | 1 | 137500 |
| B45 | 15000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B46 | 15000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B47 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B48 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |
| B49 | 35000 | 15000 | Instagram | US | 1100 | 1 | 11000 |

### Other Options
- larger_profile_alternative: diff=2100.5, warnings=0, note=Uses a broad mix of tiers.
- best_mathematical_fit: diff=100.5, warnings=1, note=Highly concentrated tier mix
- fallback_option: diff=100.5, warnings=1, note=Highly concentrated tier mix
- balanced_option: diff=7600.5, warnings=0, note=Uses a broad mix of tiers.
- current_workbook_mix: diff=13100.5, warnings=1, note=Highly concentrated tier mix

### Warnings and Diagnostics
- Search strategy: bounded_beam_search (bounded=True, approximate=True, global_optimality_guaranteed=False)
- Beam width: 1000; expanded=119065; retained=1000
- Baseline comparison for best mathematical fit: improves
- Recommended differs from best mathematical fit: yes
- Strategic warnings: best_mathematical_fit: Highly concentrated tier mix; fallback_option: Highly concentrated tier mix; current_workbook_mix: Highly concentrated tier mix
- Result warnings: none
