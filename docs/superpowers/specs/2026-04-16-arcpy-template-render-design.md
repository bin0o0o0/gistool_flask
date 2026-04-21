# ArcPy Template Render Design

**Date:** 2026-04-16

**Goal**

Make the ArcPy backend meaningful for this project by rendering from a real ArcGIS Pro template project instead of returning a placeholder failure. Scope `B` means the renderer must open a template `.aprx`, replace the business layers for the current job, and export a PNG from a real layout.

**Chosen approach**

Use a template-copy workflow anchored on the user-provided ArcGIS Pro project:

- Template project: provided by the request field `template_project` or by the `ARCPY_TEMPLATE_PROJECT` environment variable.
- Required template items:
  - map: `地图`
  - layout: `布局`
  - map frame: `地图框`

For every render job, the CLI will copy the template `.aprx` into the job directory, operate only on the copy, add the current job's data sources into the target map, set the map frame extent, export the layout to PNG, and write `result.json`.

**Why this approach**

- It works with the user's actual ArcGIS Pro 3.0.1 environment.
- It avoids mutating the source template during background jobs.
- It keeps ArcPy work isolated to a job-specific artifact folder, which is easier to debug and clean up.
- It does not depend on `ArcGISProject.createMap` / `createLayout`, which are not available on the installed runtime.

**Out of scope for this phase**

This phase does not yet implement:

- title text mapping
- legend configuration
- scale bar configuration
- fine-grained station symbology and labeling
- long-term template authoring automation

Those belong to the future `C` scope after the template-based export path is stable.

**Data flow**

1. API accepts uploads and a render request.
2. `JobService.create_job()` resolves `file_id` values into on-disk paths and writes `job.json`.
3. The ArcPy CLI receives:
   - `--config`
   - `--output-png`
   - `--result-json`
   - `--backend arcpy`
4. The ArcPy renderer:
   - copies the template `.aprx` into the job directory
   - opens the copied project
   - locates `地图`, `布局`, and `地图框`
   - clears existing non-basemap business layers from `地图`
   - adds basin boundary, river network, and station layers from `job.json`
   - computes a useful extent from the added layers
   - applies that extent to `地图框`
   - exports the layout to PNG
   - writes a structured success or failure `result.json`

**Failure handling**

The CLI must always write `result.json`, even when ArcPy rendering fails.

Expected failure categories:

- ArcPy import/runtime failure
- missing template path
- template missing required map/layout/map frame
- unsupported or unreadable input data
- layout export failure

Each failure should include a machine-readable `status=failed` response and a human-readable `error` message.

**Testing strategy**

- Keep existing stub CLI tests unchanged.
- Add focused unit tests around the ArcPy execution path using fakes/stubs for the ArcPy project API.
- Verify:
  - template path is used
  - template is copied into the job directory
  - required map/layout/map frame names are enforced
  - layer-add order is correct
  - export is attempted
  - success and structured failure `result.json` are both written

**Implementation notes**

- Introduce explicit ArcPy template configuration instead of hard-coding the template path deep in the renderer.
- Keep the CLI thin, but move ArcPy-specific orchestration into dedicated helper functions so the flow is testable without a real ArcPy runtime.
- Operate only on the copied `.aprx`, never on the source template.
