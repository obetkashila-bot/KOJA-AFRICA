KOJA AFRICA — GLOBAL LOADING ENGINE V1

Purpose
- Adds one shared, lightweight loading system across the Flask application.
- Does NOT show a full-screen spinner on every page.

Behavior
1. Internal page navigation: thin KOJA progress bar at the top.
2. Form submissions: submit button changes to Processing… and disables to prevent duplicate submissions.
3. Existing fetch/AJAX requests are NOT automatically blocked or covered by a global loader.
4. Provides window.kojaLoading.start(), .done(), and .inline() for modules that need explicit loading states.
5. Includes reusable .koja-skeleton and .koja-loading-inline CSS classes.
6. Respects prefers-reduced-motion through the existing global motion rule.

This package is based on the current KOJA Business Specific Workspaces V1 app and keeps the existing Business Connect SQL migration.
