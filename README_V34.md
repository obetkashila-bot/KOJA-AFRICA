# KOJA CLOUD v34 — Native Node Operations

Base: verified KOJA CLOUD v26.3 Media/Broadcast source.

## v34 changes
- Adds Infrastructure → Nodes dashboard.
- Uses the existing native node registry; does not register a duplicate node.
- Adds real node health and FFmpeg action jobs.
- Every node action creates a real native job ID and immediately redirects to `/jobs/<job_id>`.
- Job page polls the real native job state/result every 2 seconds.
- Adds `/api/v34/nodes`, `/api/v34/nodes/<node_id>/actions`, `/api/v34/nodes/<node_id>/jobs`, `/api/v34/jobs/<job_id>`.
- Adds compatibility for `X-KOJA-NODE-KEY` in addition to `X-KOJA-Node-Token`.

## Existing node
The upgrade is designed to use the existing KOJA NODE already registered in the native node database. It does not create another node.

## Important
The Render control plane only queues execution. Heavy FFmpeg and 24/7 media work must execute on KOJA NODE. The node worker must lease `native_node_jobs` and return results to the native result endpoint.
