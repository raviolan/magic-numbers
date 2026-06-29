Update profiles/agency fee/budget tiers:
Edit src/ui_model_adapter.py.

  That file contains the budget/profile/agency fee preset rules near the top, in SIMPLIFIED_PRESET_VALUES

  The Streamlit UI in src/app.py reads those resolved values, but the actual rule table lives in
  ui_model_adapter.py.

Start project:
 Run this from the repo root:
  streamlit run src/app.py
