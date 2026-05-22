# Watershed Layer Tree Interaction Design

Date: 2026-05-22

## Goal

Refine the `/watershed-extract` map legend into a step-aware layer tree that can drill into individual features and stay in sync with map interactions.

## Core Rule

The right-side layer tree and the map must never bind to a fixed file such as `sub_catchment.geojson`.

They must always bind to the current active step result:

1. Step 1: uploaded boundary preview only
2. Step 2: `step0_streams` preview outputs
3. Step 3: `step1.outputs`
4. Step 4: `step2.outputs`

The UI always uses the latest available result set and rebuilds its feature lists when the active result changes.

## Interaction Model

The legend becomes a collapsible tree with four groups:

- Boundary / sub-watersheds
- Reaches
- Junctions
- Break points

Each group:

- can be expanded or collapsed
- keeps its layer visibility toggle
- shows a single-select feature list when data exists

Feature labels:

- prefer `id`
- then `name`
- then `ID`
- otherwise fall back to generated labels

## Map/List Sync

Single selection only.

When the user clicks a list item:

- the corresponding map feature is highlighted
- the map fits to that feature
- the same item becomes selected in the tree

When the user clicks a map feature:

- the corresponding item becomes selected in the tree
- the feature is highlighted
- the map does not auto-fit again

## Hover Card

Hover summaries appear only for:

- sub-watersheds
- reaches

They do not appear for:

- junctions
- break points

The hover card stays lightweight and only shows a short type label plus the primary feature identifier.

## Data Flow

Frontend computes a unified `activePreviewState`:

1. `step2.outputs`
2. else `step1.outputs`
3. else `step0` preview layers
4. else uploaded boundary preview

The map component and layer tree both read from the same normalized state so the legend, selection model, and visible vector layers always describe the same result set.

## Implementation Notes

- Keep OpenLayers rendering inside `WatershedPreviewMap.vue`
- Extract the right-side tree into a focused component if needed
- Normalize feature metadata in a utility so label extraction and selection IDs stay stable
- Preserve existing click-to-add break point behavior for Step 3

## Verification

- unit tests for feature normalization and active preview selection
- existing frontend tests remain green
- build passes
- browser check confirms:
  - per-step data source switching
  - list-to-map highlight and fit
  - map-to-list selection sync
  - hover card for sub-watersheds and reaches only
