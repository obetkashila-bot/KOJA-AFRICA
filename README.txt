KOJA AFRICA — AFRICA NOW SERVER-RENDER FIX

Purpose:
- The API is already returning items, but the browser page stays on its old loading screen.
- This package renders one cached item directly into the HTML on the server, so the first story is visible even if browser JavaScript does not run.
- JavaScript then refreshes from /api/nexus/africa-now and rotates stories every 30 seconds.
- The API result is balanced so vacancies cannot occupy every slot when news is available.

Deploy:
1. Extract this ZIP.
2. Replace the production repository app.py with this app.py.
3. Commit and push to the branch connected to Render.
4. Wait for deployment and health check to finish.
5. Open https://koja-africa.onrender.com/nexus in a new tab or refresh the page.

This package has Python syntax validation only; it has not been deployed to your account. Keep your existing Render environment variables and requirements.txt.
