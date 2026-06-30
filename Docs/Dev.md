# Dev log — bugs-python branch

Chronological record of multi-step changes made to the Python port of Packard
Bugs on branch `bugs-python`. Each entry pairs a task with a short summary of
the resulting change in the tree. Newest at the bottom.

## Session — 2026-04-20

Original user request (five feature items + two add-ons):

1. Double the width of probe windows — the Python-backed sim is fast enough
   that the extra horizontal detail is cheap.
2. Give access to the original CocoaBugs food PNG templates.
3. Switch LUT neighborhood from Von Neumann (5-bit, 32 genes) to Moore
   (9-bit, 512 genes), accepting ~16× genome memory.
4. Add a "bug coloring" probe modeled after the CocoaBugs
   `BugsColoringWindowController`: user toggles a 3×3 neighborhood template
   that selects a LUT index; probe plots the histogram of per-bug move
   outputs at that index.
5. Add a scalar time-series probe window with multiple colored traces
   (population, total food-in-bugs).

Add-ons agreed during the session:

6. Fix the recipe format so the VN→Moore change can't silently load
   incompatible runs.
7. Update documentation for all of the above.

Implementation order (chosen to let each task smoke-test against the previous
one): 1 → 2 → 5 → 3 → 4 → 6 → 7.

### Task #6 — Double `PROBE_W` (512 → 1024)

- `Bugs/python/controls.py`: `PROBE_W = 1024`.
- `Bugs/python/sdl_worker.py`: `PROBE_W = 1024`; probe windows stack in the
  same column with the new width.
- All existing probes (`activity`, `q_activity`) re-verified at the new
  width.

### Task #7 — PNG food templates

- `Bugs/python/bugs_py.py`:
  - Added `_REPO_ROOT` and `_FOOD_TEMPLATES` mapping built-in names
    (`stripes`, `r-pentomino`, `big_box`, `3x3_boxes`, `empty_boxes`) to the
    `CocoaBugs/*.png` files shipped with the original distribution.
  - New `food_templates()` listing and `_load_food_png(path_or_name, N)`
    using Pillow (auto-resizes to `N×N`).
  - `state()` extended with `food_source='template'` + `template=` kwarg, and
    `brightness=` now accepts a string path (loaded as PNG).
- Requires `pip install pillow`.

### Task #8 — Scalar time-series probe

- `Bugs/python/controls.py`:
  - `_AVAILABLE_PROBES['ts']`.
  - Traces declared as `_TS_TRACES = ('population', 'food_bug')` with colors
    `_TS_COLORS = (0xFF44DD44, 0xFFFFAA22)`.
  - Shared-memory block `ts_shm = cursor:int32 + 2 × PROBE_W × float32`.
  - `_record_probes()` samples `get_population()` and `get_food_bug()` each
    tick and advances the ring cursor.
- `Bugs/python/sdl_worker.py`:
  - Argparse `--ts=<shm_name>`.
  - `_render_ts(dst, trace_bufs, cursor, global_max)` draws log-Y scrolling
    polylines with a shared Y scale.
- On-save handler writes `probe_ts.png`; `<| ts |>` buttons halve/double the
  shared Y scale.

### Task #9 — Moore neighborhood (LUT 32 → 512)

- `Bugs/C/bugs.h`: `N_GENES 32` → `N_GENES 512` (with `2^9` comment).
  Docstring rewritten with the 9-bit visual-reading-order bit table
  (NW=bit 0 … SE=bit 8), y increasing upward.
- `Bugs/C/bugs.c`: `neighborhood_gene()` expanded from 5 cells to 9 cells,
  bit masks 1, 2, 4, 8, 16, 32, 64, 128, 256 for NW, N, NE, W, C, E, SW, S,
  SE.
- `Bugs/python/bugs_py.py`: new module constants `NBHD = 'moore'`,
  `NBHD_BITS = 9`, `N_GENES = 1 << NBHD_BITS`. Docstring updated.
- Smoke-tested: grids of 64–256 run at plausible populations; genome memory
  ≈16× previous, still negligible at these N.

### Task #10 — Fix recipes for Moore change

- Recipe format bumped to `version: 2`, with new `nbhd` and `n_genes`
  fields.
- `import_run()` raises `ValueError` on nbhd mismatch ("genome structure
  differs") so v1 / VN recipes can't silently replay against the Moore
  runtime.
- Round-trip test + tampered-recipe test both pass.

### Task #11 — Bug-coloring probe with template

- `Bugs/C/bugs.h`, `bugs.c`:
  - Added `void bugs_bug_coloring_hist(int gene_idx, int32_t *hist_out);`.
  - Fills a 31×31 `int32` buffer with the per-bug `(dx, dy)` distribution
    from `genome.genes[gene_idx]` across the live population; out-of-range
    `gene_idx` yields an all-zero histogram.
- `Bugs/python/bugs_py.py`: ctypes binding + `Bugs.bug_coloring_hist(idx)`
  returning an `(31, 31) int32` numpy array.
- `Bugs/python/controls.py`:
  - `_AVAILABLE_PROBES['coloring']`, labels `NW … SE`, shared-memory block
    `coloring_shm = lut_idx:int32 + 31*31 × int32`.
  - 3×3 `GridBox` of `ToggleButton`s; toggling bits updates `coloring_idx[0]`
    (bit-packed in the same NW..SE order as the neighborhood table).
  - `_record_probes()` calls `bug_coloring_hist(coloring_idx[0])` each tick
    and writes into shm.
- `Bugs/python/sdl_worker.py`:
  - Argparse `--coloring=<shm_name>`.
  - `_render_coloring(dst, hist, lut_idx)` draws a log1p-scaled grayscale
    31×31 grid, a center crosshair at `(0, 0)`, and a miniature inset of the
    3×3 template so you can read back which bits are on.
- Invariant `hist.sum() == population` verified; sum over all 512 indices
  equals `pop × 512`.

### Task #12 — Documentation

- `Bugs/Bugs.md`:
  - Extensions list now covers Moore LUT, `ts` + `coloring` probes, PNG
    templates, and recipe v2.
  - Model section: 5-bit VN table replaced with the 9-bit Moore (NW..SE)
    table; step-list references `genes[9-bit-neighborhood]`.
  - `state(...)` signature adds `food_source='template'` + string
    `brightness=` paths.
  - New "Built-in templates" subsection lists the bundled PNG names.
  - Probes section adds `ts` (population, food-in-bugs) and `coloring`
    (3×3 template → 31×31 move histogram) and notes `PROBE_W = 1024`.
  - Recipes section documents v2 format and the `ValueError` guard.
- `Bugs/test.ipynb`:
  - §9 Moore / bug-coloring histogram with assertion
    `hist.sum() == pop` and cross-check
    `sum over all LUT indices == pop × N_GENES`.
  - §10 `food_templates()` + `run_with_controls` enabling all four probes
    on the `r-pentomino` template.
  - §11 recipe v2 round-trip + tampered-`nbhd` recipe raising `ValueError`.
- `Docs/Dev.md`: this file.

## Session — 2026-04-20

### Task #13–#15 — Split activity probe into G (whole-genome) and g (per LUT-slot)

Bedau/Packard-style activity was a single probe with ambiguous semantics.
Renamed the existing whole-genome FNV-1a content-hash probe to **G-activity**
(keeps its symbols in C for churn-avoidance) and added a parallel
**g-activity** probe keyed on `(9-bit Moore neighborhood, dx, dy)`
(i.e. the `(input, output)` LUT-slot actually used by a live bug this tick).

- `Bugs/C/bugs.c` + `bugs.h`:
  - New static hash table `gact_*` parallel to `act_*` (insert/resize/compact).
  - `g_pair_key(nbhd, dx, dy)` packs 32-bit key: high-bit guard + 9-bit nbhd
    + (dx+15) + (dy+15); avoids ACT_EMPTY=0 sentinel.
  - `bugs_g_activity_update` walks live bugs, computes `neighborhood_gene()`,
    looks up `genes[idx]`, bumps bucket.
  - Public API mirrors G-activity: `bugs_g_activity_update`,
    `bugs_g_activity_render_col`, `bugs_g_activity_get`,
    `bugs_gq_activity_deciles`, `bugs_set_g_act_ymax`, `bugs_get_g_act_ymax`.
  - `bugs.h` block comment calls out why C symbols stay `bugs_activity_*`.
- `Bugs/python/bugs_py.py`:
  - Renamed `activity_update/get_activity/q_activity_deciles` →
    `G_activity_update/get_G_activity/Gq_activity_deciles` (C-level binding
    names unchanged).
  - Added `g_activity_update`, `get_g_activity` (returns `{'key','activity',
    'pop_count','color'}` — note `key` vs `hash`; `max_n` default 8192 but
    real populations easily exceed that, pass 200000+ for headless work),
    `gq_activity_deciles`, `update_g_act_ymax`, `update_G_act_ymax`.
  - `import_run()` migrates legacy recipes: probe keys `activity` →
    `G-activity`, `q_activity` → `Gq-activity`. No recipe version bump.
- `Bugs/python/controls.py`:
  - `_AVAILABLE_PROBES` split: `G-activity`, `Gq-activity`, `g-activity`,
    `gq-activity`, plus existing `ts`/`coloring`.
  - Parallel shm blocks and cursors for all four probes; ymax buttons
    `G_act_ymax` and `g_act_ymax`.
  - `_record_probes()` covers all four (with `if not X_enabled: update()`
    fallbacks so deciles still work without the strip chart enabled).
  - `on_save` refactored via `_save_deciles()` helper; writes
    `probe_Gq_activity.png` and `probe_gq_activity.png`.
  - CLI flags `--G-activity=`, `--Gq-activity=`, `--g-activity=`,
    `--gq-activity=`.
- `Bugs/python/sdl_worker.py`:
  - Factored window creation into `_create_probe_window(title, w, h, label)`
    — collapses 4 near-identical blocks and calibrates title-bar height
    once on the first successful window.
  - 4 probe windows stacked top-down left of main (G, g, Gq, gq) at
    `ACT_H=2×PROBE_H` / `PROBE_H` respectively.
  - Shared `_render_q_activity` handles both Gq and gq decile rendering.
- `Bugs/test.ipynb`:
  - All probe keys and API calls renamed.
  - New §8 sub-section "G-activity vs g-activity" showing the distinction:
    distinct genome count (G) vs distinct `(nbhd, dx, dy)` motif count (g).
- Smoke-test: N=64, 20 steps, density 0.2 → pop 807, `g['pop_count'].sum()`
  = 807 (matches), 120 distinct motifs, 807 distinct genome hashes.

### Semantics note

- **G-activity**: counter per whole-genome content hash; bumped by `+1` per
  live bug per tick (so `Σ G_pop_count == population`). Rediscovery of an
  extinct genome reuses its bucket — "seeing rediscovery is good."
- **g-activity**: counter per `(input, output)` LUT-slot pair; bumped by
  `+1` per live bug per tick for *the slot the bug uses this tick*. Distinct
  genomes that share a motif contribute to the same bucket. `Σ g_pop_count
  == population` still holds.

## Session — 2026-04-21 — egenome (per-position food thresholds)

User request: replace the scalar `food_threshold` with a length-9 per-
Moore-position vector — the *egenome*, by analogy with EvoCA. Each bug
carries its own egenome; at birth the child's egenome is the parent's
plus i.i.d. truncated-Gaussian drift per entry with width `mu_egenome`
(clipped to `[0, 1]`). With `mu_egenome = 0` children copy exactly; with
`mu_egenome > 0` perception itself evolves.

Clarifications from the user:
1. Eliminate the scalar `food_threshold` (and its slider) entirely.
   Introduce `egenome_init` as an API-only metaparam (no GUI), plus
   helpers: `egenome_center_only`, `egenome_constant`, `egenome_random`.
2. Inheritance at birth: Gaussian drift only — no separate mutation rate.
3. Keep the egenome *out* of the G-content hash (so G-activity still
   tracks the 512-gene content, not perception).
4. Add a probe window: 9 translucent colored bands, centerlines at the
   per-position population mean, band half-width = population std.

Changes:

- `Bugs/C/bugs.h`:
  - New `#define EGENOME_N 9`.
  - Removed `bugs_set_food_threshold` / `bugs_get_food_threshold`.
  - Added: `bugs_set_mu_egenome`, `bugs_get_mu_egenome`,
    `bugs_set_egenome_init(const float *)`, `bugs_get_egenome_init(float *)`,
    `bugs_egenome_stats(float *mean, float *std)` (length EGENOME_N).
- `Bugs/C/bugs.c`:
  - Per-bug `float egenome[9]` on `bug_t`.
  - Globals: `g_mu_egenome = 0`, `g_egenome_init[9] = {0.1, …, 0.1}`.
  - `rng_gauss()` Box-Muller helper.
  - `neighborhood_gene()` rewritten to take `const bug_t *b` and test
    `F(neighbor_p) > b->egenome[p]` per position. Two call sites updated.
  - `egenome_mutate_copy(dst, src, sigma)` — per-entry truncated-Gaussian
    drift, clipped to `[0, 1]`. Called after `genome_mutate_copy` on birth.
  - Seeding copies `g_egenome_init` into each new bug's egenome.
  - `bugs_egenome_stats` uses double accumulators (`var = E[X²]-E[X]²`,
    clamped ≥0).
  - Smoke test on C side: center-only egenome → mean[C]=0.5, stds=0 at
    seed time. Drift accrues with reproduction.
- `Bugs/python/bugs_py.py`:
  - `EGENOME_N = 9`. Helpers `egenome_center_only`, `egenome_constant`,
    `egenome_random`.
  - `_DEFAULTS`: drop `food_threshold`, add `mu_egenome = 0.0`.
    `_EGENOME_INIT_DEFAULT` = `[0.1]*9` as a class attribute (non-scalar
    metaparam handled separately from the scalar-loop defaults).
  - ctypes bindings for `bugs_set_mu_egenome` / `bugs_get_mu_egenome` /
    `bugs_set_egenome_init` / `bugs_get_egenome_init` /
    `bugs_egenome_stats`.
  - `Bugs.set_egenome_init(v)`, `Bugs.get_egenome_init()`,
    `Bugs.egenome_stats() → (mean, std)` accessor (both length-9 float32).
  - `Bugs.init(N, …, egenome_init=…)` accepts the vector and logs it into
    `_init_metaparams`; `sim.state(…, egenome_init=…)` re-applies at seed
    time and stores the active value in `_state_params` for recipe export.
  - `update_mu_egenome` slider-update helper.
  - `params_str()` prints `egenome_init` with a `# default` annotation
    when it differs from the class default.
  - Recipe bumped to `version: 3`. `metaparams_final` carries the
    `egenome_init` vector. `import_run` migrates legacy v1/v2 recipes:
    `food_threshold` → `egenome_init = [ft]*9` + `mu_egenome = 0`.
- `Bugs/python/controls.py`:
  - Slider `sl_food_threshold` → `sl_mu_egenome` (range 0–0.1, step 0.001).
  - Added probe name `'egenome'` to `_AVAILABLE_PROBES` (description:
    "9 translucent position bands (mean ± std)").
  - Shared memory layout: 4 B cursor + 9× mean float32[PROBE_W] +
    9× std float32[PROBE_W].
  - `_record_probes` pulls `sim.egenome_stats()` and writes a column.
  - On-restart zeroes cursor + buffers. Cleanup unlinks the shm.
  - `on_save`: writes `probe_egenome.png` with 9 mean lines + translucent
    mean±std fills, linear Y in `[0,1]`.
- `Bugs/python/sdl_worker.py`:
  - `--egenome=<shm>` CLI flag.
  - `_EG_RGB` — 9-color palette keyed to `[NW, N, NE, W, C, E, SW, S, SE]`.
  - `_render_egenome(dst, means, stds, cursor)`: software-blends 9 bands
    onto a float workspace (α = 0.30 for bands, 1.0 for centerlines), adds
    y = 0.25/0.50/0.75 gridlines, packs back to ARGB int32. Linear Y in
    `[0, 1]`.
  - Window title "egenome (mean +/- std, 9 positions)", stacked in
    between gq-activity and ts. Destroyed + shm closed on exit.
- `Bugs/Bugs.md`:
  - Quick-start `sim.init(...)` now shows `mu_egenome`, `egenome_init`,
    and the three helper imports.
  - Neighborhood section: bit *p* set iff `F(neighbor_p) > egenome[p]`.
  - Metaparam table: `food_threshold` row → `mu_egenome` row. New
    "Egenome (API-only, no slider)" subsection documenting the vector
    semantics, inheritance rule, and default.
  - New probes section `### egenome`.
  - Probe-enable snippet includes `'egenome': True`.
- `Bugs/test.ipynb`:
  - §3 params dict: `food_threshold = 0.2` → `mu_egenome = 0.02` +
    `egenome_init = [0.1]*9`.
  - New §12 "Egenome — per-position food thresholds with Gaussian drift"
    demonstrating the three helpers and `sim.egenome_stats()` before/after
    400 steps of drift.

Smoke tests:
- C: `clang … -dynamiclib` clean build. Minimal C program confirms
  `bugs_set_egenome_init` + `bugs_seed_with_density` propagate to every
  bug's egenome and `bugs_egenome_stats` reports the expected mean/std.
- Python: `sim.init(..., mu_egenome=0.02)` + `state(egenome_init=
  egenome_constant(0.1))` + 500 steps → std[C] converges to ~0.02
  (matching the σ) while mean stays ~0.1 (no systematic drift bias).
- `controls.py` and `sdl_worker.py` import cleanly.


## Session — 2026-04-24 — Channon-style neutral shadow (N-activity)

### Task #1 — Add neutral shadow + N-activity probe to Bugs and EvoCA

Goal: install a calibration shadow that mirrors the real run's demography
under random selection, and expose an N-activity probe that bucketises the
shadow's genome content with the same hash as G-activity, so the two
distributions live in the same magnitude space.

Design (locked before coding, parallel in both projects):
- Shadow stores full genome content (Bugs: `genome_t`; EvoCA: `LUT_BYTES`)
  + cached FNV-1a hash. No positions, food, egenome, age, or alive flag.
- `*_neutral_enable()` seeds the shadow by copying current real genomes /
  alive-cell LUTs 1:1, so t₀ distributions are identical.
- Mirror is automatic inside `bugs_step` / `evoca_step` after real
  `g_births_last` / `g_deaths_last` are tallied. Deaths: uniform-random
  swap-and-pop. Births: append, parent picked uniformly with replacement,
  same `genome_mutate_copy` / Poisson-bit-flip mutation as the real run
  (EvoCA respects `restricted_mu` using the real run's `n_active`).
- N-activity buckets use the same hash and table pattern as G-activity
  (`nact_*` parallel to `act_*`, no flux history in v1).
- For EvoCA, `evoca_step` had no birth/death counters — added globals
  `g_births_last` / `g_deaths_last` and accessors. Births = every Phase-4
  reproduction; deaths = tax-deaths + alive-child evictions, so
  `births - deaths == net Δalive` and the shadow stays population-locked.

Ref: Channon, "Passing the ALife test: Activity statistics classify
evolution in Geb as unbounded" (ECAL 2001) — §2.2.

Files touched:
- `cocoabugs/Bugs/C/bugs.h`, `bugs.c`: forward decls for `nact_*` /
  `neut_*`; `act_reset/free` siblings extended for nact + neut; mirror
  call appended at end of `bugs_step`; new ~280-line block defining
  `bugs_neutral_*`, `bugs_n_activity_*`, `bugs_nq_activity_deciles`,
  `bugs_set/get_n_act_ymax`.
- `cocoabugs/Bugs/python/bugs_py.py`: ctypes signatures + Python methods
  `neutral_enable/disable/is_enabled/population`, `N_activity_update`,
  `get_N_activity`, `Nq_activity_deciles`.
- `EvoCA/C/evoca.h`, `evoca.c`: same pattern (uses `act_entry_t` already
  defined in evoca.c). Added `evoca_get_births_last/deaths_last`. Hooked
  `evoca_init` / `evoca_free` / `evoca_step`.
- `EvoCA/python/evoca_py.py`: ctypes signatures + Python methods
  `get_births_last/deaths_last`, `neutral_*`, `n_activity_update`,
  `get_n_activity`, `nq_activity_deciles`.

Smoke tests:
- Bugs: 96×96 grid, food_inc=0.05, mu=0.02, 3000 steps. Real pop=792,
  shadow=761 (small drift from pre-existing `place_or_bump` silent-drop
  when a moving parent fails to place — not introduced here). G/N
  activity distributions roughly co-located at this depth.
- EvoCA: 64×64, GoL LUT, food_inc=0.12, m_scale=0.4, mu_lut=0.001,
  tax=0.05, 2000 steps. ~1.05M cumulative births/deaths each, shadow
  tracks real exactly at 4096. G live buckets=415 vs N live=255;
  G_max_activity=2015 vs N_max_activity=1061. Gq deciles*D = [1,1,2,3,
  5,8,12,21,40], Nq*D = [0,1,1,2,3,5,9,16,33] — real run consistently
  ~20% higher across deciles, with a fatter tail. Matches the Channon
  expectation that adaptive selection produces longer-lived genome
  lineages than random demography.

Out of scope for v1 (deferred):
- N-activity flux probe / pop_hist ring buffer (G-activity has one).
- Shared `act_table.h` header across the two projects — would refactor
  `act_*` + `gact_*` + `nact_*` into a single reusable struct. Hold
  off until a third user lands and the API is settled.
- Render-column wiring into `sdl_worker.py` + `controls.py` for both
  projects (probes only run from notebook code currently).

Discussion notes:
- We considered a simpler shadow (no genome, one activity counter per
  individual = lifespan). Rejected after reading Channon §2.1: per-
  individual buckets would not share a magnitude space with G-activity
  and so cannot calibrate the [a₀, a₁] "significant new activity" band
  in the way the shadow is meant to.
- For Bugs at default mutation rate (0.02 × 512 ≈ 10 mutations/birth),
  identical-genome inheritance is rare in either real or shadow, so the
  G/N distributions don't sharply diverge in short runs. EvoCA with
  mu_lut=0.001 (~0.25 expected mutations / birth) shows a visible
  divergence within 2000 steps because identical-LUT inheritance is the
  norm and selection vs. drift produces clearly different lineage
  persistences.


## Session — 2026-04-25 — Wire N-activity and Nq-activity probes into SDL

### Task #1 — Bugs SDL: add N-activity and Nq-activity windows

Bugs `controls.py`:
- Registered `'N-activity'` and `'Nq-activity'` in `_AVAILABLE_PROBES`.
- Allocated `N_activity_shm` (4 B cursor + ACT_H × PROBE_W × 4 B int32) and
  `Nq_activity_shm` (4 B cursor + 9 × PROBE_W × 4 B float32), parallel to
  the existing G/Gq blocks.
- Added `--N-activity=` / `--Nq-activity=` to the `cmd` line.
- Added `_record_probes` branches that call
  `sim._lib.bugs_n_activity_update`, `bugs_n_activity_render_col`, and
  `bugs_nq_activity_deciles` and write into the shm buffers.
- Added `_save_deciles("Nq_activity", ...)` to `on_save`.
- `on_restart` zeros the new buffers and re-attaches the neutral shadow
  (`bugs_init` frees it; we rebuild with `sim.neutral_enable()`).
- If either N-probe is enabled at startup, `sim.neutral_enable()` is called
  once before the SDL subprocess launches.

Bugs `sdl_worker.py`:
- Parses `--N-activity=` / `--Nq-activity=`, opens the shms via the
  existing `_open_activity_shm` and `_open_deciles_shm` helpers.
- Creates two new windows (titles: `N-activity (shadow)` / `Nq-activity
  (shadow)`), stacked between Gq and g for visual comparison with the
  real-run probes above and below. Render path scrolls the int32 strip
  via `np.roll` (same as G), and uses `_render_q_activity` for the
  decile lines (same as Gq).

### Task #2 — EvoCA SDL: add n_activity and nq_activity windows

EvoCA `controls.py`:
- Registered `'n_activity'` and `'nq_activity'` in `_AVAILABLE_PROBES`.
- Allocated parallel shms (same layouts as Bugs).
- Wired `--n-activity=` / `--nq-activity=` to the cmd line.
- `_record_probes` writes a column per tick using `evoca_n_activity_*`
  and `evoca_nq_activity_deciles`.
- `on_restart` zeros buffers and re-attaches the neutral shadow.
- `sim.neutral_enable()` called once at session start when probes on.

EvoCA `sdl_worker.py`:
- Parses `--n-activity=` / `--nq-activity=` (lower-case to match the
  project's existing convention).
- Opens the two shms, creates two SDL windows (titles `n_activity
  (shadow)` / `nq_activity (shadow)`) in the existing inline-creation
  style. Placed right after the q_activity window in the vertical stack.
- Render loop scrolls the strip and renders deciles via the existing
  `_render_q_activity` helper.
- Cleanup destroys both new windows and closes their shms.

Smoke tests:
- `python3 -c "import controls; print(available_probes())"` for both
  projects — both now list the new probe names alongside existing ones.
- Bugs probes registry: `['G-activity', 'Gq-activity', 'N-activity',
  'Nq-activity', 'g-activity', 'gq-activity', 'egenome', 'ts',
  'coloring']`.
- EvoCA probes registry now includes `'n_activity'` and `'nq_activity'`
  immediately after `'q_activity'`.

Files touched:
- `cocoabugs/Bugs/python/controls.py`
- `cocoabugs/Bugs/python/sdl_worker.py`
- `EvoCA/python/controls.py`
- `EvoCA/python/sdl_worker.py`

How to use (notebook, Bugs):
```python
sim = Bugs(); sim.init(N=96, …); sim.set_food_source(...);
sim.seed_with_density(0.3)
run_with_controls(sim, probes={'G-activity': True, 'Gq-activity': True,
                               'N-activity': True, 'Nq-activity': True})
```
The N/Nq windows render the Channon shadow's whole-genome activity
distribution and its decile profile alongside G/Gq from the real run.
EvoCA: same, but probe keys are `'n_activity'` / `'nq_activity'`.

Out of scope (deferred):
- N-activity flux probe + ring buffer (G-activity has one in C; not yet
  built for the shadow).
- A combined "G vs N" overlay panel (current design renders the two as
  separate strip charts in the stack).
