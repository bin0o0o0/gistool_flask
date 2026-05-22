# Watershed Layer Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a step-aware layer tree for `/watershed-extract` that lists individual features, syncs selection with the map, and shows hover cards for sub-watersheds and reaches.

**Architecture:** Keep OpenLayers rendering inside the existing preview map component, but move step-aware data normalization into a shared utility so both the map and the layer tree operate on the same derived state. The map component will own selected and hovered feature state, rebuild its tree from the current active preview result, and preserve existing Step 3 click-to-add break-point behavior.

**Tech Stack:** Vue 3, TypeScript, OpenLayers, Vitest

---

### Task 1: Step-aware preview normalization

**Files:**
- Modify: `frontend/src/utils/watershedMap.ts`
- Modify: `frontend/src/tests/watershedMap.test.ts`

- [ ] Add a normalization layer that derives the current preview groups from `step2.outputs -> step1.outputs -> step0 previews -> uploaded boundary preview`.
- [ ] Represent each group with stable feature ids, display labels, and access to the original GeoJSON feature.
- [ ] Cover the source-priority logic and feature-label fallback logic in `watershedMap.test.ts`.

### Task 2: Layer tree and selection interaction

**Files:**
- Modify: `frontend/src/components/WatershedPreviewMap.vue`

- [ ] Replace the flat legend buttons with collapsible groups for boundary/sub-watersheds, reaches, junctions, and break points.
- [ ] Support per-group visibility toggle plus per-feature single selection.
- [ ] When a list item is selected, highlight the map feature and fit the map to it.
- [ ] When a map feature is clicked, highlight the matching list item without re-fitting.

### Task 3: Hover card behavior

**Files:**
- Modify: `frontend/src/components/WatershedPreviewMap.vue`

- [ ] Add pointer hover detection for boundary/sub-watershed and reach features only.
- [ ] Show a lightweight hover card with type label and primary id/name.
- [ ] Do not show hover cards for junctions or break points.

### Task 4: Verification

**Files:**
- Modify as needed: `frontend/src/tests/watershedMap.test.ts`

- [ ] Run `npm run test`.
- [ ] Run `npm run build`.
- [ ] Capture a browser screenshot of `http://127.0.0.1:5173/watershed-extract` and confirm the layer tree renders cleanly.
