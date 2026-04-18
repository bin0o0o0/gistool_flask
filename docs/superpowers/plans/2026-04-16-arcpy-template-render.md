# ArcPy Template Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder ArcPy backend with a template-copy renderer that opens a real `.aprx`, injects job data, and exports a PNG.

**Architecture:** Keep the Flask/API job orchestration unchanged, but make the CLI's ArcPy path load a configured template project and operate on a per-job copied project. Encapsulate ArcPy-specific orchestration behind helper functions so the code can be unit tested with fake ArcPy objects.

**Tech Stack:** Python, Flask, pytest, ArcPy (`arcpy.mp`) on ArcGIS Pro 3.0.1

---

### Task 1: Add configuration for the ArcPy template project

**Files:**
- Modify: `basin_map_tool/config.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
def test_app_config_exposes_arcpy_template_path():
    from basin_map_tool.config import AppConfig

    config = AppConfig.from_mapping(
        {
            "ARCPY_TEMPLATE_PROJECT": r"D:\template\project.aprx",
        }
    )

    assert str(config.arcpy_template_project) == r"D:\template\project.aprx"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_cli.py -k template_path`
Expected: FAIL because `AppConfig` has no `arcpy_template_project`

- [ ] **Step 3: Write minimal implementation**

Add `arcpy_template_project: Path | None` to `AppConfig` and load it from `ARCPY_TEMPLATE_PROJECT`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_cli.py -k template_path`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add basin_map_tool/config.py tests/test_cli.py
git commit -m "feat: add arcpy template project config"
```

### Task 2: Add failing tests for ArcPy template-copy rendering orchestration

**Files:**
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add tests that:

```python
def test_run_arcpy_copies_template_and_exports_png(tmp_path, monkeypatch):
    ...

def test_run_arcpy_writes_structured_failure_when_template_items_missing(tmp_path, monkeypatch):
    ...
```

The tests should stub ArcPy objects and assert that:

- the template is copied
- the copied project path is opened
- layers are added from `job.json`
- layout export is called with the requested PNG path
- failures still produce `result.json`

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_cli.py -k arcpy`
Expected: FAIL because the current ArcPy path only writes placeholder failure output

- [ ] **Step 3: Write minimal test doubles**

Create simple fake classes inside the test file for:

- fake project
- fake map
- fake layout
- fake map frame
- fake camera

- [ ] **Step 4: Re-run tests to verify the failures are about missing production behavior**

Run: `pytest -q tests/test_cli.py -k arcpy`
Expected: FAIL on missing copy/export/layer orchestration, not test setup errors

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: cover arcpy template render flow"
```

### Task 3: Implement ArcPy helper functions and result writing

**Files:**
- Modify: `basin_map_tool/render/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for success payload details**

Extend the ArcPy success test to assert:

```python
assert payload["status"] == "succeeded"
assert payload["output_png"] == str(output_png)
assert payload["feature_counts"]["station_layers"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_cli.py -k arcpy`
Expected: FAIL because success payload is not generated from a real ArcPy flow

- [ ] **Step 3: Write minimal implementation**

Implement in `basin_map_tool/render/cli.py`:

- a template-path resolver
- a helper that copies the template `.aprx`
- a helper that opens the copied project through `arcpy.mp.ArcGISProject`
- a helper that finds `地图`, `布局`, and `地图框`
- a helper that clears existing non-basemap layers
- a helper that adds basin, river, and station layers
- a helper that exports the layout
- shared helpers to write success/failure `result.json`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_cli.py -k arcpy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add basin_map_tool/render/cli.py tests/test_cli.py
git commit -m "feat: implement arcpy template render flow"
```

### Task 4: Wire the template configuration into app/runtime defaults

**Files:**
- Modify: `basin_map_tool/config.py`
- Modify: `README.md`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for default template handling**

```python
def test_app_config_defaults_arcpy_template_project_to_none():
    from basin_map_tool.config import AppConfig

    config = AppConfig.from_mapping({})

    assert config.arcpy_template_project is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_cli.py -k default_template`
Expected: FAIL until the config contract is explicit

- [ ] **Step 3: Write minimal implementation**

Keep the template path optional in config, but document that production ArcPy rendering requires it to be set.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_cli.py -k default_template`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add basin_map_tool/config.py README.md tests/test_cli.py
git commit -m "docs: document arcpy template project setting"
```

### Task 5: Run verification for stub and ArcPy-focused tests

**Files:**
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run focused CLI tests**

Run: `pytest -q tests/test_cli.py`
Expected: PASS

- [ ] **Step 2: Run API smoke tests that should remain unaffected**

Run: `pytest -q tests/test_api.py`
Expected: PASS

- [ ] **Step 3: Inspect the rendered result shape**

Confirm the ArcPy success path writes:

```json
{
  "status": "succeeded",
  "output_png": "...",
  "feature_counts": {
    "station_layers": 1
  }
}
```

- [ ] **Step 4: Record any environment-dependent limits**

Note that full end-to-end ArcPy rendering still depends on the real template file and readable GIS inputs on the host machine.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_cli.py basin_map_tool/render/cli.py basin_map_tool/config.py
git commit -m "test: verify arcpy template render integration"
```
