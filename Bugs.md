# Bugs — Packard Bugs in C + Python

A port of the CocoaBugs "Packard Bugs" model (Bedau–Packard 1991 variant) to a
reusable C core with a Python frontend. The original Objective‑C / Cocoa
implementation lives in `plugins/Packard Bugs/` and is described in detail in
`../Docs/cocoabugs.md`.

**Extensions beyond the Obj‑C original:**

- Float food field `F(x) ∈ [0, 1]` with additive regrowth (`food_inc`) toward a
  fixed target `F_source`. Obj‑C had a static binary food bit.
- Optional diffusion of the food field (`gdiff` passes per tick).
- SplitMix64 RNG with `bugs_set_seed(...)` — Obj‑C used unseeded `random()`.
- 9‑bit **Moore** neighborhood (3×3) indexing a 512‑gene LUT per bug
  (Obj‑C used a 5‑cell Von Neumann plus‑shape → 32 genes).
- Per‑genome **G‑activity** probe (whole‑genome FNV‑1a content hash)
  with hash‑color strip chart.
- Per‑LUT‑slot **g‑activity** probe: one bucket per `(neighborhood, dx, dy)`
  (input, output) pair actually used by the population — the action‑level
  analogue of G‑activity.
- 9‑decile quantile versions of both (`Gq‑activity`, `gq‑activity`).
- Scalar time‑series probe (`ts`) with multiple colored traces (population,
  total food‑in‑bugs).
- Bug‑coloring probe (`coloring`): user picks a 9‑bit LUT index via a
  clickable 3×3 template; probe plots a 31×31 histogram of per‑bug `(dx, dy)`
  move outputs at that index.
- Built‑in PNG food templates from the original CocoaBugs distribution
  (`food_source='template'`).
- Recipe file format v2 with nbhd compatibility guard.

## Layout

```
Bugs/
├── Bugs.md              ← this file
├── Makefile             ← builds libbugs.{dylib,so}
├── C/
│   ├── bugs.h           ← public API
│   ├── bugs.c           ← implementation
│   └── libbugs.dylib    ← built artifact
└── python/
    ├── bugs_py.py       ← ctypes wrapper (class Bugs)
    ├── controls.py      ← ipywidgets panel + sim thread
    └── sdl_worker.py    ← SDL2 renderer subprocess
```

## Build

```
cd Bugs/
make           # produces C/libbugs.dylib on macOS, C/libbugs.so on Linux
make clean
```

Requires a C compiler with `-fPIC`, `-dynamiclib` (macOS) or `-shared` (Linux),
and `libm`.

## Python requirements

```
pip install numpy ipywidgets matplotlib pysdl2 pysdl2-dll
```

`pysdl2-dll` ships SDL2 binaries so no system SDL install is needed.

## API reference

### Constructing the simulator

```python
sim = Bugs(lib_path=None)
```

The constructor *only* takes `lib_path` — metaparams are not accepted here.
If `lib_path` is `None`, `libbugs.dylib`/`.so` is located relative to
`bugs_py.py`.

### Initializing

```python
sim.init(
    N,                       # grid size (positional)
    mutation_rate     = 0.02,
    reproduction_food = 20.0,
    movement_cost     = 0.5,
    eat_amount        = 2.0,
    initial_food      = 10.0,
    food_inc          = 0.01,
    mu_egenome        = 0.0,                     # σ of per-entry Gaussian drift at birth
    gdiff             = 0,
    move_range        = 15,
    egenome_init      = [0.1] * 9,               # per-Moore-position food thresholds
)
```

Helpers for common `egenome_init` regimes:

```python
from python.bugs_py import (
    egenome_center_only,   # only the center (C/self) entry set; others zero
    egenome_constant,      # all 9 entries = same value (reproduces scalar
                           # food_threshold behavior when value=0.1)
    egenome_random,        # each entry i.i.d. uniform on [0, 1]
)
```

Any metaparam can be overridden via kwarg. **Passing a dict**: use `**`
unpacking — `sim.init(100, **my_params)`. Unknown kwargs raise `TypeError`.

After `init`, metaparams are accessible as attributes (`sim.food_inc`, ...)
and can be live-updated via `sim.update_food_inc(v)`, etc. The `update_*`
methods push changes through to the C library; direct attribute assignment
does *not* — always use the updaters.

### Seeding the food field and population

```python
sim.state(
    food_source         = 'uniform',   # 'uniform' | 'brightness' | 'custom' | 'template'
    food_source_value   = 1.0,         # used when food_source='uniform'
    food_source_thresh  = 0.5,         # used when food_source in {'brightness', 'template'}
    brightness          = None,        # (N,N) float32, or flat, or a PNG path (str)
    template            = None,        # name from food_templates() when food_source='template'
    seed_density        = 0.1,         # per-cell probability of placing a bug
)
```

`sim.state(...)` also stashes its arguments in `sim._state_params` so
`Restart` and `export_recipe` can replay the same setup.

### RNG seeding

```python
sim.set_seed(42)   # call before state() for deterministic seeding
```

Only seeds the C RNG; if you use numpy or `random` in your own setup code,
seed those separately.

### Running one step / colorizing

```python
sim.step()
sim.colorize(pixels, colormode=0)   # fills pixels[N*N] int32 ARGB in place
```

### Getters

```python
sim.N                  # grid size (property)
sim.cell_px            # screen pixels per cell (property, from C CELL_PX)
sim.get_step()         # uint32 tick counter
sim.get_population()   # current bug count
sim.get_births_last()  # births on most recent step
sim.get_deaths_last()  # deaths on most recent step
sim.get_food_bug()     # Σ food over all alive bugs
sim.get_food_env()     # Σ F(x) over the grid
sim.get_food_field()   # (N,N) float32 copy of F
sim.get_food_source()  # (N,N) float32 copy of F_source
sim.get_bug_mask()     # (N,N) uint8 copy; 1 where a bug is present
```

### Probes (programmatic)

```python
# G-activity: one bucket per whole-genome content hash
sim.G_activity_update()                 # bucketize one tick
G = sim.get_G_activity(max_n=4096)      # {'hash','activity','pop_count','color'}
sim.Gq_activity_deciles()               # float32[9]: p10..p90 of G-activity
sim.update_G_act_ymax(y)                # strip Y-axis scale

# g-activity: one bucket per (nbhd, dx, dy) LUT-slot actually used
sim.g_activity_update()                 # bucketize one tick
g = sim.get_g_activity(max_n=200000)    # {'key','activity','pop_count','color'}
sim.gq_activity_deciles()               # float32[9]: p10..p90 of g-activity
sim.update_g_act_ymax(y)                # strip Y-axis scale
```

### Recipe export/import

```python
path = sim.export_recipe("descriptor", probes={...}, colormode=0)
# → ../Runs/YYYY-MM-DD_descriptor.bugs

from python.bugs_py import import_run
sim, display_kwargs = import_run("../Runs/....bugs")  # recipe='final' (default): explored state
sim, display_kwargs = import_run("../Runs/....bugs", recipe='init')   # original t=0 params

import_run()   # no args: list available .bugs files under Runs/
```

### Teardown

```python
sim.free()
```

Also called implicitly on `__del__`. If a display is running,
`free()`/`init()` first call `sim._stop_display()` to shut it down.

## Quick start (Jupyter)

```python
import sys; sys.path.insert(0, '.')
from python.bugs_py import Bugs
from python.controls import run_with_controls

sim = Bugs()
sim.init(256, food_inc=0.05, mutation_rate=0.01)
sim.state(food_source='uniform', food_source_value=1.0, seed_density=0.2)

run_with_controls(sim, cell_px=2,
                  probes={'G-activity': True, 'Gq-activity': True,
                          'g-activity': True, 'gq-activity': True})
```

The cell returns immediately; widgets render below it, an SDL2 window opens,
and the simulation runs in a background thread. Call `sim.free()` in a later
cell to tear everything down.

## Display scale

`CELL_PX` in `bugs.h` defaults to 4 (screen pixels per simulation cell).  Set
`cell_px=` on `run_with_controls(...)` to override at runtime — important for
large grids: a 512×512 sim at `CELL_PX=4` is a 2048×2048 window.

| N   | cell_px=1 | cell_px=2 | cell_px=4 |
|-----|-----------|-----------|-----------|
| 100 |  100²     |   200²    |   400²    |
| 256 |  256²     |   512²    |  1024²    |
| 512 |  512²     |  1024²    |  2048²    |

## Model (condensed)

N×N periodic grid. Each cell has a float food value `F(x) ∈ [0, 1]`. Each
bug carries **512 genes** indexed by a **9‑bit Moore neighborhood** pattern
(the full 3×3 including self), in visual reading order with y increasing
upward:

| bit | neighbor                |
|-----|-------------------------|
| 0   | `F(x-1, y+1)`  (NW)     |
| 1   | `F(x,   y+1)`  (N)      |
| 2   | `F(x+1, y+1)`  (NE)     |
| 3   | `F(x-1, y  )`  (W)      |
| 4   | `F(x,   y  )`  (C/self) |
| 5   | `F(x+1, y  )`  (E)      |
| 6   | `F(x-1, y-1)`  (SW)     |
| 7   | `F(x,   y-1)`  (S)      |
| 8   | `F(x+1, y-1)`  (SE)     |

A bit is set when `F(neighbor) > egenome[p]`, where `egenome` is the bug's
own length‑9 threshold vector — one entry per Moore position. Each gene
encodes one of 120 moves (8 directions × 15 magnitudes). Per tick:

1. Food regenerates toward `F_source`: `F ← min(F + food_inc, F_source)`.
2. Optional `gdiff` passes of a 4‑neighbor diffusion stencil.
3. Bugs act in random order:
   - If `food ≤ 0`: die.
   - If `food > reproduction_food`: split — parent's `food /= 2`, child takes
     the other half and is placed at the parent's cell.
   - Eat: `eat = min(eat_amount, F(cell))`; subtract `eat` from the cell, add
     to the bug. Food *is* consumed from the cell — unlike the Obj‑C original
     where the food bit was static.
   - Lose `movement_cost` (always applied, whether or not the bug ate — the
     Obj‑C original only charged it off‑food).
   - Look up `genes[9-bit-neighborhood]`, move.

See `../Docs/cocoabugs.md` §4–§5 for the reference semantics of the Obj‑C
model and how this port diverges.

## Metaparameters

All are live‑editable via the controls panel sliders; the `update_*` methods
on `Bugs` push changes to the C library without restarting.

| Parameter           | Default | Range (slider) | Meaning                                              |
|---------------------|---------|----------------|------------------------------------------------------|
| `mutation_rate`     | 0.02    | 0.0 – 0.1      | Per‑gene‑slot replacement probability on birth.      |
| `reproduction_food` | 20.0    | 1 – 60         | `food > this` triggers reproduction.                 |
| `movement_cost`     | 0.5     | 0 – 5          | Food subtracted per tick regardless of eating.       |
| `eat_amount`        | 2.0     | 0 – 10         | Max food transferred from cell to bug per tick; actual = `min(eat_amount, F(cell))`. |
| `initial_food`      | 10.0    | 0 – 30         | Food on each newly seeded bug.                       |
| `food_inc`          | 0.01    | 0 – 0.2        | Food regrown per cell per tick (additive, capped).   |
| `mu_egenome`        | 0.0     | 0 – 0.1        | σ of per‑entry truncated‑Gaussian drift applied to the child's egenome at birth. `0` = exact copy (no perception evolution). |
| `gdiff`             | 0       | 0 – 10         | Diffusion passes per tick on `F`.                    |
| `move_range`        | 15      | 1 – 15         | Caps newly-drawn gene magnitudes to `1..move_range`. `1` = Moore‑neighbor moves only (8 outcomes); `15` = full 8×15 = 120‑move space. Affects gene generation; existing genes keep their magnitudes until mutated. |

### Egenome (API-only, no slider)

`egenome_init` is a length‑9 vector of per‑Moore‑position food thresholds
`[θ_NW, θ_N, θ_NE, θ_W, θ_C, θ_E, θ_SW, θ_S, θ_SE]`, each in `[0, 1]`.
Each bug carries its own copy (the *egenome*, by analogy with EvoCA), and
the perception bit for position `p` flips when `F(neighbor_p) > egenome[p]`.

At birth, the child's egenome is the parent's plus an i.i.d. truncated
Gaussian perturbation per entry with σ = `mu_egenome`, clipped to `[0, 1]`.
With `mu_egenome = 0` the child copies exactly — the egenome acts as a
static perception parameter. With `mu_egenome > 0`, perception itself
evolves: the fitness landscape depends on which positions the bug can
distinguish between food and no‑food.

Set via API (there is no slider): `sim.init(..., egenome_init=...)` or
`sim.set_egenome_init(v)` before seeding. The default
(`[0.1] × 9`) reproduces the historical scalar `food_threshold = 0.1`.

`food_inc` is additive (not proportional): at 0.01, a fully depleted cell
takes 100 ticks to recover to `F_source = 1`. At low values bugs collapse
before food recovers — for fast populations, try 0.05–0.1.

## Food source

`sim.state(...)` sets up both the target field `F_source` and the initial bug
population:

```python
sim.state(food_source='uniform', food_source_value=1.0, seed_density=0.2)

sim.state(food_source='brightness', brightness=img_array, food_source_thresh=0.5,
          seed_density=0.2)   # image-driven: dark pixels → food=1

sim.state(food_source='brightness', brightness='path/to/image.png',
          food_source_thresh=0.5, seed_density=0.2)   # PNG path fallback

sim.state(food_source='template', template='r-pentomino',
          food_source_thresh=0.5, seed_density=0.2)

sim.state(food_source='custom', brightness=my_array, seed_density=0.2)  # raw
```

`brightness` / custom arrays must be `(N, N)` or flat length `N*N`, `float32`
in `[0, 1]`.  When `brightness=` is a string, it is treated as a PNG path and
loaded (and resized to `N×N`) via Pillow.

### Built‑in templates

`bugs_py.food_templates()` returns the list of bundled names (PNGs copied from
the original CocoaBugs distribution):

- `stripes`
- `r-pentomino`
- `big_box`
- `3x3_boxes`
- `empty_boxes`

These are loaded from `../CocoaBugs/*.png` relative to the repo root.

## Probes

### `G-activity` (whole‑genome content)

Per‑genome activity hash table. For each live bug per tick, the bug's full
512‑byte gene array is hashed (FNV‑1a over content); the bucket for that
hash is incremented by one. Rendered as a scrolling strip, bar color keyed
off the hash — a given genotype keeps its color as it scrolls, and
rediscovery of an extinct genome reuses its original bucket/color. Use the
`G_act_ymax <| / |>` buttons to adjust the per‑bar Y scaling.

### `Gq-activity` (G‑activity deciles)

Population‑level G‑activity deciles p10..p90 on a log‑Y scrolling chart.
Each color is one decile (blue = p10, green = p50, red = p90). Useful for
seeing when a few dominant genotypes pull away from the bulk — watch the
p90 line diverge from the median.

### `g-activity` (per LUT‑slot)

Per‑`(input, output)` activity. For each live bug per tick, we look up its
current 9‑bit Moore neighborhood (the "input"), read the gene at that LUT
index to get `(dx, dy)` (the "output"), and increment the bucket keyed by
`(nbhd, dx, dy)`. Same scrolling‑strip visualisation as G‑activity, but the
buckets now represent behavioural motifs ("when I see *this* pattern, I
move *this* way") that cut across genome identity — distinct genomes
sharing a motif land in the same bucket. Use the `g_act_ymax <| / |>`
buttons to adjust scaling.

### `gq-activity` (g‑activity deciles)

Population‑level g‑activity deciles p10..p90 (log‑Y scrolling). Analogous
to Gq‑activity but over the motif distribution.

### `egenome`

Per‑Moore‑position egenome population statistics. Each of the 9 positions
`[NW, N, NE, W, C, E, SW, S, SE]` gets its own translucent colored band:
centerline = population mean of `egenome[p]`, band half‑width = population
std dev, on a linear Y axis in `[0, 1]`. Useful for watching which
neighbor positions the population has committed to (narrow band near 0 or
near 1 = everyone distinguishes/ignores that position), which are still
under selection (band drifting), and which stay neutral (wide band).

Requires `mu_egenome > 0` for the bands to spread. Per‑position color
palette is stable across runs.

### `ts`

Scalar time‑series probe — multiple colored traces overlaid on one log‑Y
scrolling chart, sharing the `PROBE_W` pixel width. Current traces:

- `population` — alive bug count (green)
- `food_bug`   — total food summed over alive bugs (orange)

The Y‑scale is shared across traces and adjustable via the `<| ts |>` buttons.

### `coloring`

Bug‑coloring probe. A 3×3 GridBox of toggle buttons (labelled NW..SE) lets you
pick which of the nine Moore‑neighborhood bits are "on"; the resulting 9‑bit
value selects one of the 512 LUT indices. Each tick the probe computes a
31×31 histogram of per‑bug `(dx, dy)` outputs from `genes[lut_idx]` across the
live population, rendered as a log1p grayscale grid with a center crosshair at
`(0, 0)`. A miniature copy of the selected 3×3 template is inset in the corner
so you can read back which neighborhood pattern you're probing.

This is the numerical analogue of the CocoaBugs `BugsColoringWindowController`,
but instead of literally coloring bugs, it visualises the distribution of
motions a population would take if every bug saw the selected neighborhood.

Enable probes:

```python
run_with_controls(sim, probes={'G-activity':  True, 'Gq-activity': True,
                               'g-activity':  True, 'gq-activity': True,
                               'egenome': True,
                               'ts': True, 'coloring': True})
```

Probe sub‑windows render at `PROBE_W = 1024` pixels wide (doubled from the
previous 512) — the Python‑backed simulator is fast enough that the extra
horizontal detail is cheap.

## Recipes (reproducible runs)

`export_recipe(descriptor)` writes a JSON recipe file to `../Runs/` capturing
the current metaparams (initial + final), food source configuration, seed
density, enabled probes, and color mode:

```python
sim.export_recipe("drought-recovery",
                  probes={'G-activity': True, 'g-activity': True},
                  colormode=1)
# → ../Runs/2026-04-20_drought-recovery.bugs
```

Load and replay:

```python
from python.bugs_py import import_run
sim, display_kwargs = import_run("../Runs/2026-04-20_drought-recovery.bugs")
run_with_controls(sim, **display_kwargs)
```

`import_run()` with no arguments lists available recipes.

### Recipe format v2

Recipes now carry a `version` field, plus `nbhd` (e.g. `'moore'`) and
`n_genes` (e.g. `512`). `import_run()` raises `ValueError` if the recipe's
`nbhd` does not match the running C core's neighborhood — this guards against
silently loading a 32‑gene VN recipe into the 512‑gene Moore runtime. Older
v1 recipes (pre‑Moore) will be rejected; regenerate them with a current build.

For byte‑identical reproducibility, set a seed before `state(...)`:

```python
sim.set_seed(42)
sim.state(...)
```

(Note: `state()` itself uses the RNG via `seed_with_density`, so seed *before*
it.)

## Controls panel reference

| Widget        | Action                                                              |
|---------------|---------------------------------------------------------------------|
| Run / Pause   | Toggle simulation loop.                                             |
| Restart       | Re‑init C lib with current slider metaparams, re‑run the original `state()`, t=0. |
| Step          | Single tick when paused.                                            |
| Quit          | Tear down SDL window and shared memory.                             |
| Save Plots    | Write `probe_*.png` in cwd for any scalar probes active.            |
| descriptor    | Text used as the recipe filename.                                   |
| Export        | Write a `.bugs` recipe file.                                        |
| Color         | `red-bugs` / `genome-hash` / `bug-food`.                            |
| `<| name |>`  | Halve / double probe Y‑axis scale.                                  |

Sliders auto‑pause on touch and auto‑resume 200 ms after the last change, so
you can drag without the sim running away.

**Restart semantics.** Metaparams bound to sliders (`mutation_rate`,
`reproduction_food`, `movement_cost`, `eat_amount`, `initial_food`, `food_inc`,
`mu_egenome`, `gdiff`, `move_range`) are pushed into the re‑initialized C core
at their *current* slider values — so any tweaks you made persist across a
restart. Seeding and field setup (`seed_density`, `food_source`,
`food_source_value`, `egenome_init`) revert to the arguments of the *original*
`sim.state(...)` call, since those aren't slider‑backed. Net effect: restart
reseeds the same spatial/genomic initial conditions under whatever
metaparameter knobs you've dialed in.

## Architecture

```
Main process (Jupyter kernel)
├── ipywidgets callbacks       ← fire in the kernel event loop
├── Sim thread                 ← sim.step() + colorize() → shared memory
├── Reader thread              ← relays SDL worker stdout to terminal
└── subprocess (sdl_worker.py)
    └── SDL2 main thread       ← reads shared memory, renders windows
```

SDL2 on macOS must run on thread 0, which belongs to the Jupyter kernel.
Running SDL2 anywhere else crashes the kernel, so rendering is moved to a
subprocess that owns its own main thread. Pixel data and probe buffers cross
the boundary via POSIX `multiprocessing.shared_memory` — no copying.

`ctrl_shm` is a 5×int32 array used for bidirectional signaling:

| index | field     | direction          |
|-------|-----------|--------------------|
| 0     | quit      | either side → quit |
| 1     | colormode | main → worker      |
| 2     | step_cnt  | main → worker      |
| 3     | fps × 10  | main → worker      |
| 4     | paused    | main → worker      |

## Current limits

- No bug‑level observation of other bugs (same as original — input is
  food‑only).
- "Stay" is not in the action alphabet — every bug moves each tick.
- Pool resolution of conflicting placements is random Moore‑neighbor recursion
  (bounded depth issues possible at extreme density).
- `set_seed()` seeds the C RNG but `numpy`/`random` in Python are not reset;
  fully reproducible runs require seeding both sides if either is used.
- SDL2 main window closes the whole session (probe sub‑windows can be closed
  individually without killing the main loop).

## See also

- `../Docs/cocoabugs.md` — reference semantics of the original Obj‑C model.
- `../CocoaBugs/` — the historical Xcode application.
- `../../EvoCA/` — sibling project using the same ipywidgets+SDL subprocess
  architecture; `Bugs/python/controls.py` is adapted from its `controls.py`.
