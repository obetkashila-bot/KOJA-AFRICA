KOJA AFRICA — RESEARCH 2090 PRODUCTION INTEGRATION

Base:
app(20260918-140633).py (latest supplied KOJA production app)

Integration:
The Research 2090 visual layer and Research All-in-One routes are integrated into the main app.py.
All non-Research KOJA modules remain from the production base.

Research capabilities present in this build include the existing Research system plus the unified Research, workspace, history, related questions, compare, export and API layers already present in the All-in-One build.

No destructive SQL migration is included.
No other KOJA service was intentionally replaced.

Validation:
- Python AST parse passed.
- py_compile passed.
