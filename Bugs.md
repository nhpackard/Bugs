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
- Per‑genome activity probe with hash‑color strip chart.
- 9‑decile quantile activity probe (`q_activity`).

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
    food_threshold    = 0.1,
    gdiff             = 0,
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
    food_source         = 'uniform',   # 'uniform' | 'brightness' | 'custom'
    food_source_value   = 1.0,         # used when food_source='uniform'
    food_source_thresh  = 0.5,         # used when food_source='brightness'
    brightness          = None,        # (N,N) or flat float32 in [0,1]
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
sim.activity_update()                # bucketize one tick of activity
table = sim.get_activity(max_n=4096) # {'hash','activity','pop_count','color'}
sim.q_activity_deciles()             # float32[9]: p10..p90
sim.update_act_ymax(y)               # per-bar Y-axis scale in the strip
```

### Recipe export/import

```python
path = sim.export_recipe("descriptor", probes={...}, colormode=0)
# → ../Runs/YYYY-MM-DD_descriptor.bugs

from python.bugs_py import import_run
sim, display_kwargs = import_run("../Runs/....bugs")   # recipe='init' (default)
sim, display_kwargs = import_run("../Runs/....bugs", recipe='final')  # use post-drag params

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
                  probes={'activity': True, 'q_activity': True})
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
bug carries 32 genes indexed by a 5‑bit neighborhood pattern:

| bit | neighbor               |
|-----|------------------------|
| 0   | `F(x, y+1)`  (up)      |
| 1   | `F(x-1, y)`  (left)    |
| 2   | `F(x,   y)`  (self)    |
| 3   | `F(x+1, y)`  (right)   |
| 4   | `F(x, y-1)`  (down)    |

A bit is set when `F(neighbor) > food_threshold`. Each gene encodes one of
120 moves (8 directions × 15 magnitudes). Per tick:

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
   - Look up `genes[5-bit-neighborhood]`, move.

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
| `food_threshold`    | 0.1     | 0 – 1          | `F > threshold` → gene bit set.                      |
| `gdiff`             | 0       | 0 – 10         | Diffusion passes per tick on `F`.                    |

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

sim.state(food_source='custom', brightness=my_array, seed_density=0.2)  # raw
```

`brightness` / custom arrays must be `(N, N)` or flat length `N*N`, `float32`
in `[0, 1]`.

## Probes

### `activity`

Per‑genome activity hash table. Each living bug's genome is hashed; per‑hash
cumulative activity (ticks alive) is rendered as a scrolling strip, with the
bar color keyed off the hash (so a given genotype keeps its color as it
scrolls). Use the `act_ymax <| / |>` halve/double buttons to adjust the Y
scaling.

### `q_activity`

Population‑level activity deciles p10..p90 on a log‑Y scrolling chart. Each
color is one decile (blue = p10, green = p50, red = p90). Useful for seeing
when a few dominant genotypes pull away from the bulk — watch the p90 line
diverge from the median.

Enable both:

```python
run_with_controls(sim, probes={'activity': True, 'q_activity': True})
```

## Recipes (reproducible runs)

`export_recipe(descriptor)` writes a JSON recipe file to `../Runs/` capturing
the current metaparams (initial + final), food source configuration, seed
density, enabled probes, and color mode:

```python
sim.export_recipe("drought-recovery", probes={'activity': True}, colormode=1)
# → ../Runs/2026-04-20_drought-recovery.bugs
```

Load and replay:

```python
from python.bugs_py import import_run
sim, display_kwargs = import_run("../Runs/2026-04-20_drought-recovery.bugs")
run_with_controls(sim, **display_kwargs)
```

`import_run()` with no arguments lists available recipes.

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
| Restart       | Re‑init C lib with current metaparams, re‑run saved `state()`, t=0. |
| Step          | Single tick when paused.                                            |
| Quit          | Tear down SDL window and shared memory.                             |
| Save Plots    | Write `probe_*.png` in cwd for any scalar probes active.            |
| descriptor    | Text used as the recipe filename.                                   |
| Export        | Write a `.bugs` recipe file.                                        |
| Color         | `red-bugs` / `genome-hash` / `bug-food`.                            |
| `<| name |>`  | Halve / double probe Y‑axis scale.                                  |

Sliders auto‑pause on touch and auto‑resume 200 ms after the last change, so
you can drag without the sim running away.

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
