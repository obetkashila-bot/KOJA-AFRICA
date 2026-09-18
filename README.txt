KOJA AFRICA Research V8 - Research Notes Runtime Fix

Fixes the Render 500 on /research/notes caused by research_ai_notes calling a missing _gemini_text helper.

The notes engine now uses KOJA's existing _ai_call provider/fallback chain and keeps the evidence-only fallback if AI is unavailable.

No SQL migration.
Existing Research V7 functionality is preserved.
