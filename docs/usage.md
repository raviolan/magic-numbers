# Optimizer CLI Usage

## Local app prototype (Phase 4A)

Install Streamlit in your local environment if needed:

```bash
pip install streamlit
```

Run the local app:

```bash
streamlit run src/app.py
```

App modes:
- `Existing canonical sheet`: loads campaigns from `data/normalized/canonical_normalized_models.json`.
- `Manual campaign builder`: enter campaign fields and profile rows in-table, then run the same optimizer in-memory.

Manual builder workflow:
1. Campaign budget
2. Channel selection
3. CPM setup
4. Profile structure
5. Optimizer settings (advanced)
6. Current setup
7. Run optimizer
8. Results + approve calculation

Channel selection guardrail:
- Manual builder now requires explicit channel selection before CPM setup.
- Default selected channels:
  - Instagram: selected
  - TikTok: selected
  - YouTube: not selected
- At least one channel must be selected.
- Selected channels control:
  - which CPM inputs are shown
  - which optional channel split inputs are shown
  - which channels are used by generated profile rows
- If profile rows contain an unselected channel, optimization is blocked until rows are fixed/regenerated.

Manual builder budget rule wording:
- UI label: `Profile fee deduction (%)` (default `7.5`).
- This is the same workbook rule as multiplier `0.925`.
- Mapping: `multiplier = 1 - deduction_percent / 100`.
- The app displays a budget breakdown:
  - Total budget
  - Agency fee
  - Included paid media
  - Remaining profile-fee base
  - Profile fee deduction (7.5% default)
  - Available profile-fee target

Manual builder fee input modes:
- Agency fee:
  - Fixed amount
  - Percentage of budget
  - Percentage range (for example `29-35%` with a step such as `0.5`)
- Paid media:
  - Fixed amount
  - Percentage of budget
  - Percentage range (for example `10-15%`)
- Default mode for both agency fee and paid media is `Percentage of budget`.
- Default percentages:
  - Agency fee: `32%`
  - Paid media: `15%`

Range behavior:
- The app expands percentage ranges to concrete values using the configured step.
- It evaluates all agency-fee / paid-media combinations.
- It runs the existing optimizer for each combination and picks the best recommended result.
- Selected values are shown in the results:
  - selected agency fee amount (+ percent when applicable)
  - selected paid media amount (+ percent when applicable)
  - number of combinations evaluated
- Safety guard: maximum `200` combinations by default. If exceeded, narrow ranges or increase step.

Project CPM setup:
- Set default CPM per supported channel before row generation:
  - Instagram CPM
  - TikTok CPM
  - YouTube CPM
- CPM setup includes a currency selector for library medians:
  - default currency is `SEK`
  - switch to `EUR` when needed
- `Use library medians` fills project CPM inputs from current library medians for the selected currency.
- Library median helper text is shown per channel.
- CPM setup only renders fields for selected channels.
- Generated rows inherit CPM from these project-level values.
- Profile rows are generated automatically from Profile structure and use current project CPM values.
- Switching CPM medians or project CPM values updates future auto-generated rows.
- Validation rule: CPM must be set (>0) for channels used in rows. Unused channel CPM may be blank.

Manual builder amount input formatting:
- Major amount fields are text inputs with flexible parsing:
  - `1000000`
  - `1 000 000`
  - `1000000,00`
  - `1 000 000,00`
  - `1,000,000`
- Displayed output numbers use space thousand separators, for example `1 000 000`.

Approve calculation and local CPM library:
- After running the optimizer (manual or canonical mode), use `Approve calculation`.
- `Calculation name` is required. `Optional comment` may be blank.
- `Currency` is required when approving:
  - `SEK`
  - `EUR`
- You can approve the recommended option (default) or another available option label.
- Approved calculations are stored locally in:
  - `data/library/approved_calculations.json`
- CPM observations are stored locally in:
  - `data/library/cpm_observations.json`
- CPM observations include only CPMs used by the approved option's `fill_instructions`.
- Unused project-level CPM inputs are not stored.
- The CPM library is automatically seeded with canonical/reference CPM observations from:
  - `data/normalized/canonical_normalized_models.json`
- Reference seed currency mapping:
  - `5311 Dear Dahlia Kalkyl (V.A).xlsx` -> `EUR`
  - `5312 Medclair Kalkyl (V.A).xlsx` -> `SEK`
- Unmapped canonical reference sources are seeded as `Unknown` currency.
- Seeding is idempotent: repeated app runs do not duplicate the same reference observation.
- Sidebar preview shows channel-level `Average` and `Median` CPM values separately by currency (`SEK` and `EUR`).
- Observations with `Unknown` currency are excluded from SEK/EUR summaries until tagged.
- Full CPM library view (sidebar expander `Open CPM library`) shows the `currency` column and supports manual currency tagging (`SEK`, `EUR`, `Unknown`) with `Save library changes`.
- You can add standalone reference CPM rows directly in the CPM library view via `Add reference CPM row`.
  - Required: reference/project name, channel, currency, CPM (>0)
  - Optional: market, comment
  - Stored with `source_type = manual_reference`
- You can bulk import reference CPM rows from a local workbook via `Import reference CPM sheet`.
  - Default path: `/Users/viola/Downloads/CPMreferenser.xlsx`
  - The source workbook is read-only and is never modified.
  - Supported channel aliases map to:
    - `IG` / `Instagram` -> `Instagram`
    - `TikTok` / `Tik Tok` / `TT` -> `TikTok`
    - `YouTube` / `You Tube` / `YT` -> `YouTube`
  - Supported currency aliases map to `SEK` / `EUR`; missing currency uses the selected default import currency (`SEK`, `EUR`, or `Unknown`).
  - Special mapping: `Niche` column is mapped to CPM library `Comment`.
  - Recognized column aliases include:
    - reference name: `reference`, `project`, `project name`, `calculation name`, `campaign`, `client`, `name`, `workbook`
    - channel: `channel`, `platform`, `kanal`, `plattform`
    - CPM: `cpm`, `cpm value`, `value`, `rate`
    - currency: `currency`, `valuta`, `curr`
    - market: `market`, `country`, `region`, `land`, `marknad`
    - comment: `comment`, `comments`, `notes`, `note`, `kommentar`, `niche`
  - Import supports multi-sheet workbooks and preserves source sheet name on imported rows.
  - Preview shows `valid`, `invalid`, and `duplicate` rows before import.
  - Only valid non-duplicate rows are imported, saved as `source_type = manual_reference_import`.
  - Re-importing the same workbook does not duplicate already imported rows.
- Persistence is local JSON only (no database).

Profile structure workflow:
- Set `Total number of profiles`.
- Optional `channel split` expander can define Instagram/TikTok/YouTube row counts.
- If all channel counts are blank, rows are generated with deterministic default distribution.
- If exactly one channel count is blank and others are provided, the remainder is inferred.
- Channel counts cannot exceed total profiles.
- Rows are auto-managed internally from Profile structure (`row_index` from `1..N`).
- Normal workflow does not require manual row-table interaction.

Manual mode baseline behavior:
- If all rows have valid current profile sizes, baseline comparison is available.
- If any current profile size is blank/invalid, the optimizer runs with baseline unavailable (no fake baseline is created).

Advanced optimizer settings:
- Located in the main page under `Advanced optimizer settings` (collapsed by default).
- `Optimization method`:
  - `Fast closest diff`: bounded beam search (fast, approximate, no global-optimum guarantee).
  - `Exact closest diff`: deterministic exact fee-sum search with a safe state limit.
- `Beam width`: how many mixes are kept while searching (higher can be slower but more thorough).
- `Exact search max states`: safety guard for exact mode.
- `Number of options to compare`: how many candidate options are retained for recommendation/reporting.
- `Recommendation emphasis`: `math` prioritizes closest diff, `strategic` weighs sellable mixes more.
- `Allowed profile sizes`: check/uncheck `15K`, `35K`, `75K`, `125K`, `175K` (default all selected).
  - Optimizer recommendations only use selected tiers.
  - If no tiers are selected, optimization is blocked.
  - If current baseline rows use excluded tiers, baseline is shown as unavailable for that run.
- `Allow negative diff`: permits over-budget profile-fee outcomes (usually keep off).
- `Profile fee deduction (%)` is also in Advanced settings (default `7.5`, equivalent to workbook multiplier `0.925`).

Paid media inclusion default:
- `Paid media included in target` defaults to enabled in manual builder.

## Run all canonical sheets

```bash
python3 src/optimizer.py
```

Optional tier/method flags:

```bash
python3 src/optimizer.py --optimization-method exact_closest_diff --allowed-tiers 15000,35000,75000 --max-exact-states 250000
```

Writes:
- `data/optimizer/optimizer_results.json`
- `data/optimizer/optimizer_results.md`

## Run one sheet by workbook + sheet

```bash
python3 src/optimizer.py --workbook "5312 Medclair Kalkyl (V.A).xlsx" --sheet "1.2M"
```

## Run one sheet by unique sheet name

```bash
python3 src/optimizer.py --sheet "1.2M"
```

If the sheet name matches multiple canonical sheets, the CLI fails and lists the matching workbook/sheet pairs.

## Open markdown report automatically (macOS)

```bash
python3 src/optimizer.py --sheet "1.2M" --open-report
```

If opening fails, the optimizer still completes and prints a warning.

## Output path behavior

- Multi-sheet runs: default filenames in `data/optimizer/`.
- Exactly one processed sheet: slugged filenames, for example:
  - `data/optimizer/optimizer_results_5312-medclair-kalkyl-v-a-1-2m.json`
  - `data/optimizer/optimizer_results_5312-medclair-kalkyl-v-a-1-2m.md`

This avoids overwriting the full all-sheets report on one-sheet runs.

## Report structure

The markdown report includes:
- `Executive Summary` (one row per processed sheet)
- Per-sheet sections:
  - Recommendation
  - Option Comparison
  - Fill Instructions for Recommended Option
  - Other Options
  - Warnings and Diagnostics

## Current limitations

- Canonical normalized sheets + manual campaign builder only.
- Search mode depends on selected optimization method:
  - `Fast closest diff`: bounded/approximate.
  - `Exact closest diff`: globally optimal for closest diff when the exact state limit is not exceeded.
- No workbook editing, workbook write-back, arbitrary workbook upload/parsing, or AI instruction layer.
