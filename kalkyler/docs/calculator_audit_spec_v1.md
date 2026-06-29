# Calculator Audit and V1 Specification

Generated from `kalkyler.zip` on 2026-04-24.

## Audit summary

- Workbooks scanned: 22
- Sheets scanned: 76
- Profile sections detected: 74
- Profile/CPM rows extracted: 635
- Canonical candidate sheets: 6
- Sheets with formula cache issues: 0

## Locked V1 scope

### Profile tiers

The v1 optimizer should only use the following profile-size targets:

- 15K
- 35K
- 75K
- 125K
- 175K

Legacy values such as text ranges, placeholder ranges, and non-standard sizes should be recorded as metadata only. They should not be used as optimizer targets or references for target profile mix logic.

### Channels

The v1 optimizer should only support:

- Instagram
- TikTok
- YouTube

Other channels should be classified as unsupported/reference only.

### Impression logic

Use profile size in K, rounded with MROUND to nearest 5.

- Instagram: `MROUND(profile_size * 0.7, 5)`
- TikTok: `MROUND(profile_size * 0.8, 5)`
- YouTube: `MROUND(profile_size * 0.5, 5)`

### Paid logic

- Paid before the profile section counts in the main budget calculation.
- Paid after the profile section is an add-on and should be ignored for the main optimizer.
- Overview sheets such as summary/summering tabs should be ignored.

### CPM logic

For v1, CPMs should be read from the workbook/project rather than predicted.

Future phase:
- Build a CPM reference table by market, niche, channel, profile tier, rights period, currency and campaign type.

## Classification definitions

| Classification | Meaning | V1 usage |
|---|---|---|
| canonical_candidate | Best v1 formula references from the ZIP | Use to validate optimizer math and workbook interpretation |
| usable_modern_like | Uses valid v1 profile tiers and supported channels, but not explicitly canonical | Good secondary validation set |
| usable_with_standardization | Useful profile layout, but sizes or labels need normalization | Reference only for structure and CPM observation |
| legacy_reference_only | Unsupported channels or significant legacy logic present | Do not use for target logic |
| template_blank | Template or placeholder sheet | Use only to understand layout possibilities |
| overview_ignore | Summary/overview sheet | Ignore for optimizer targets |
| unsupported_structure | No standard profile section detected | Ignore unless manually reviewed |

## Canonical candidate sheets

- `5311 Dear Dahlia Kalkyl (V.A).xlsx` / `10 profiler`: 10 profile rows, paid logic `add_on_after_profiles`, diff `H21` = -46.2, CPMs `Instagram: 46; TikTok: 35`
- `5311 Dear Dahlia Kalkyl (V.A).xlsx` / `20 profiler`: 20 profile rows, paid logic `add_on_after_profiles`, diff `H31` = 114.8, CPMs `Instagram: 46; TikTok: 35`
- `5311 Dear Dahlia Kalkyl (V.A).xlsx` / `30 profiler`: 30 profile rows, paid logic `add_on_after_profiles`, diff `H41` = 480.8, CPMs `Instagram: 46; TikTok: 35`
- `5312 Medclair Kalkyl (V.A).xlsx` / `600K`: 12 profile rows, paid logic `included_before_profiles`, diff `H34` = 1640.375, CPMs `Instagram: 1100, 800; TikTok: 1100, 800`
- `5312 Medclair Kalkyl (V.A).xlsx` / `1.2M`: 24 profile rows, paid logic `included_before_profiles`, diff `H46` = 207.375, CPMs `Instagram: 1100, 800; TikTok: 1100, 800`
- `5312 Medclair Kalkyl (V.A).xlsx` / `2M`: 30 profile rows, paid logic `included_before_profiles`, diff `H52` = 13100.5, CPMs `Instagram: 1100, 800; TikTok: 1100, 685.3, 800`


## Formula cache note

No sheets in the ZIP had formula cells missing cached values during this audit. Some sheets use shared formulas where the formula text itself is stored only on the first cell in a formula range, but the cached formula results are still present. That is usable for audit purposes.

## Recommended next step

Build a prototype sheet interpreter and optimizer against the canonical candidate sheets first, especially Medclair and Dear Dahlia. After those match workbook diff behavior, validate against usable_modern_like sheets, then expand support for paid placement and market/channel balancing.
