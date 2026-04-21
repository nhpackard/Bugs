"""
bugs_py.py — Python ctypes wrapper for the Bugs C library.

Bugs model (Packard Bugs, Bedau & Packard 1991)
----------------------------------------------
Agents live on an N×N periodic grid with a float food field F(x) ∈ [0, 1].
Each bug carries 32 movement genes indexed by a 5-bit neighborhood pattern:

    bit 0 : F(x, y+1) > food_threshold      (up)
    bit 1 : F(x-1, y) > food_threshold      (left)
    bit 2 : F(x,   y) > food_threshold      (self)
    bit 3 : F(x+1, y) > food_threshold      (right)
    bit 4 : F(x, y-1) > food_threshold      (down)

Each gene encodes one of 120 moves: 8 directions × 15 magnitudes.
"""

import ctypes
import os

import numpy as np


N_GENES  = 32
MAG_MAX  = 15
N_DIRS   = 8


def _find_lib():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, "..")
    for name in ("libbugs.dylib", "libbugs.so"):
        p = os.path.realpath(os.path.join(root, "C", name))
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "libbugs not found. Run `make` in the Bugs/ directory first.")


class Bugs:
    """Thin ctypes wrapper around the Bugs shared library."""

    _DEFAULTS = dict(
        mutation_rate=0.02,
        reproduction_food=20.0,
        movement_cost=0.5,
        eat_amount=2.0,
        initial_food=10.0,
        food_inc=0.01,
        food_threshold=0.1,
        gdiff=0,
    )

    def __init__(self, lib_path=None):
        self._lib = ctypes.CDLL(lib_path or _find_lib())
        self._N = 0
        for k, v in self._DEFAULTS.items():
            setattr(self, k, v)
        self._state_params = {}
        self._setup_signatures()

    def _setup_signatures(self):
        L = self._lib
        L.bugs_init.argtypes                 = [ctypes.c_int]
        L.bugs_init.restype                  = None
        L.bugs_free.argtypes                 = []
        L.bugs_free.restype                  = None
        L.bugs_set_seed.argtypes             = [ctypes.c_uint64]
        L.bugs_set_seed.restype              = None

        # Metaparam setters/getters
        for name in ("mutation_rate", "reproduction_food", "movement_cost",
                     "eat_amount", "initial_food", "food_inc",
                     "food_threshold"):
            sfn = getattr(L, f"bugs_set_{name}")
            gfn = getattr(L, f"bugs_get_{name}")
            sfn.argtypes = [ctypes.c_float]
            sfn.restype  = None
            gfn.argtypes = []
            gfn.restype  = ctypes.c_float
        L.bugs_set_gdiff.argtypes            = [ctypes.c_int]
        L.bugs_set_gdiff.restype             = None
        L.bugs_get_gdiff.argtypes            = []
        L.bugs_get_gdiff.restype             = ctypes.c_int

        # Food field setup
        L.bugs_set_food_source.argtypes      = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_set_food_source.restype       = None
        L.bugs_set_food_source_from_brightness.argtypes = [
            ctypes.POINTER(ctypes.c_float), ctypes.c_float]
        L.bugs_set_food_source_from_brightness.restype  = None

        # Seeding
        L.bugs_exterminate.argtypes          = []
        L.bugs_exterminate.restype           = None
        L.bugs_seed_with_density.argtypes    = [ctypes.c_float]
        L.bugs_seed_with_density.restype     = None

        # Step
        L.bugs_step.argtypes                 = []
        L.bugs_step.restype                  = None

        # Accessors
        L.bugs_get_N.argtypes                = []
        L.bugs_get_N.restype                 = ctypes.c_int
        L.bugs_get_cell_px.argtypes          = []
        L.bugs_get_cell_px.restype           = ctypes.c_int
        L.bugs_get_step.argtypes             = []
        L.bugs_get_step.restype              = ctypes.c_uint32
        L.bugs_get_population.argtypes       = []
        L.bugs_get_population.restype        = ctypes.c_int
        L.bugs_get_births_last.argtypes      = []
        L.bugs_get_births_last.restype       = ctypes.c_int
        L.bugs_get_deaths_last.argtypes      = []
        L.bugs_get_deaths_last.restype       = ctypes.c_int
        L.bugs_get_food_bug.argtypes         = []
        L.bugs_get_food_bug.restype          = ctypes.c_float
        L.bugs_get_food_env.argtypes         = []
        L.bugs_get_food_env.restype          = ctypes.c_float
        L.bugs_get_food_field.argtypes       = []
        L.bugs_get_food_field.restype        = ctypes.POINTER(ctypes.c_float)
        L.bugs_get_food_source.argtypes      = []
        L.bugs_get_food_source.restype       = ctypes.POINTER(ctypes.c_float)
        L.bugs_get_bug_mask.argtypes         = []
        L.bugs_get_bug_mask.restype          = ctypes.POINTER(ctypes.c_uint8)

        # Colorize
        L.bugs_colorize.argtypes             = [ctypes.POINTER(ctypes.c_int32),
                                                ctypes.c_int]
        L.bugs_colorize.restype              = None

        # Activity probe
        L.bugs_activity_update.argtypes      = []
        L.bugs_activity_update.restype       = None
        L.bugs_activity_render_col.argtypes  = [ctypes.POINTER(ctypes.c_int32),
                                                ctypes.c_int]
        L.bugs_activity_render_col.restype   = None
        L.bugs_activity_get.argtypes         = [
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_int]
        L.bugs_activity_get.restype          = ctypes.c_int
        L.bugs_set_act_ymax.argtypes         = [ctypes.c_int]
        L.bugs_set_act_ymax.restype          = None
        L.bugs_get_act_ymax.argtypes         = []
        L.bugs_get_act_ymax.restype          = ctypes.c_int

        # q_activity deciles
        L.bugs_q_activity_deciles.argtypes   = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_q_activity_deciles.restype    = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def init(self, N, **kwargs):
        """Initialize an N×N grid. Any metaparam from _DEFAULTS can be
        passed as a keyword argument."""
        stop = getattr(self, '_stop_display', None)
        if stop is not None:
            stop()
            self._stop_display = None
        self._N = int(N)
        self._lib.bugs_init(self._N)
        for k, default in self._DEFAULTS.items():
            val = kwargs.pop(k, default)
            setattr(self, k, type(default)(val))
            getattr(self._lib, f"bugs_set_{k}")(getattr(self, k))
        if kwargs:
            raise TypeError(f"unknown init kwargs: {sorted(kwargs)}")
        self._state_params = {}
        self._init_metaparams = {k: getattr(self, k) for k in self._DEFAULTS}

    def free(self):
        stop = getattr(self, '_stop_display', None)
        if stop is not None:
            stop()
            self._stop_display = None
        self._lib.bugs_free()
        self._N = 0

    def __del__(self):
        try:
            if self._N:
                self.free()
        except Exception:
            pass

    def set_seed(self, s):
        self._lib.bugs_set_seed(ctypes.c_uint64(int(s) & 0xFFFFFFFFFFFFFFFF))

    # ── Metaparam update helpers ──────────────────────────────────────

    def _make_updater(name, is_int=False):
        def _update(self, v):
            val = int(v) if is_int else float(v)
            setattr(self, name, val)
            getattr(self._lib, f"bugs_set_{name}")(val)
        _update.__name__ = f"update_{name}"
        return _update

    update_mutation_rate     = _make_updater("mutation_rate")
    update_reproduction_food = _make_updater("reproduction_food")
    update_movement_cost     = _make_updater("movement_cost")
    update_eat_amount        = _make_updater("eat_amount")
    update_initial_food      = _make_updater("initial_food")
    update_food_inc          = _make_updater("food_inc")
    update_food_threshold    = _make_updater("food_threshold")
    update_gdiff             = _make_updater("gdiff", is_int=True)
    del _make_updater

    def update_act_ymax(self, y):
        self._lib.bugs_set_act_ymax(int(y))

    # ── Params export ─────────────────────────────────────────────────

    def params(self):
        """Return current metaparameters as a dict suitable for init(**d)."""
        return dict(N=self._N, **{k: getattr(self, k) for k in self._DEFAULTS})

    def params_str(self):
        """Return a copy-pasteable sim.init(...) call with defaults annotated."""
        p = self.params()
        lines = ["sim.init("]
        for k, v in p.items():
            val = repr(v)
            if k in self._DEFAULTS and v != self._DEFAULTS[k]:
                lines.append(f"    {k}={val},   # default: {self._DEFAULTS[k]!r}")
            else:
                lines.append(f"    {k}={val},")
        lines.append(")")
        return "\n".join(lines)

    # ── Food field setup ──────────────────────────────────────────────

    def set_food_source(self, src):
        """Set F_source(x) ∈ [0,1]. src: (N,N) or flat float array."""
        arr = np.ascontiguousarray(np.asarray(src, dtype=np.float32).ravel())
        assert len(arr) == self._N * self._N, \
            f"need {self._N*self._N} values, got {len(arr)}"
        self._lib.bugs_set_food_source(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        self._state_params['food_source'] = 'custom'

    def set_food_source_uniform(self, v=1.0):
        """Set F_source to a uniform value on all cells."""
        arr = np.full(self._N * self._N, float(v), dtype=np.float32)
        self._lib.bugs_set_food_source(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        self._state_params['food_source'] = 'uniform'
        self._state_params['food_source_value'] = float(v)

    def set_food_source_from_brightness(self, brightness, thresh=0.5):
        """Set F_source from image brightness. Pixels with
        brightness < thresh become food (F_source=1), else 0."""
        arr = np.ascontiguousarray(
            np.asarray(brightness, dtype=np.float32).ravel())
        assert len(arr) == self._N * self._N
        self._lib.bugs_set_food_source_from_brightness(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            float(thresh))
        self._state_params['food_source'] = 'brightness'
        self._state_params['food_source_thresh'] = float(thresh)

    # ── Seeding ───────────────────────────────────────────────────────

    def exterminate(self):
        self._lib.bugs_exterminate()

    def seed_with_density(self, d):
        """Place a bug on each cell with probability d."""
        self._lib.bugs_seed_with_density(float(d))
        self._state_params['seed_density'] = float(d)

    def state(self, food_source='uniform', food_source_value=1.0,
              food_source_thresh=0.5, brightness=None,
              seed_density=0.1):
        """Initialize food field and bug population from parameters."""
        self._state_params = {}
        if food_source == 'brightness':
            if brightness is None:
                raise ValueError("food_source='brightness' requires brightness=")
            self.set_food_source_from_brightness(brightness, food_source_thresh)
        elif food_source == 'custom':
            if brightness is None:
                raise ValueError("food_source='custom' requires src array")
            self.set_food_source(brightness)
        else:
            self.set_food_source_uniform(food_source_value)
        self.exterminate()
        self.seed_with_density(seed_density)

    # ── Step and colorize ─────────────────────────────────────────────

    def step(self):
        self._lib.bugs_step()

    def colorize(self, pixels, colormode=0):
        """Fill a (N*N,) int32 numpy array with ARGB values in-place."""
        arr = np.ascontiguousarray(pixels, dtype=np.int32)
        self._lib.bugs_colorize(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            int(colormode))
        return arr

    # ── Getters ───────────────────────────────────────────────────────

    def get_food_field(self):
        """Return (N, N) float32 copy of live food field F(x)."""
        ptr = self._lib.bugs_get_food_field()
        return np.ctypeslib.as_array(ptr, shape=(self._N * self._N,)) \
                 .copy().reshape(self._N, self._N)

    def get_food_source(self):
        """Return (N, N) float32 copy of regeneration target F_source(x)."""
        ptr = self._lib.bugs_get_food_source()
        return np.ctypeslib.as_array(ptr, shape=(self._N * self._N,)) \
                 .copy().reshape(self._N, self._N)

    def get_bug_mask(self):
        """Return (N, N) uint8 copy; 1 where a bug is present."""
        ptr = self._lib.bugs_get_bug_mask()
        return np.ctypeslib.as_array(ptr, shape=(self._N * self._N,)) \
                 .copy().reshape(self._N, self._N)

    def get_step(self):
        return int(self._lib.bugs_get_step())

    def get_population(self):
        return int(self._lib.bugs_get_population())

    def get_births_last(self):
        return int(self._lib.bugs_get_births_last())

    def get_deaths_last(self):
        return int(self._lib.bugs_get_deaths_last())

    def get_food_bug(self):
        """Σ food over all alive bugs."""
        return float(self._lib.bugs_get_food_bug())

    def get_food_env(self):
        """Σ F(x) over the grid."""
        return float(self._lib.bugs_get_food_env())

    # ── Activity probe ────────────────────────────────────────────────

    def activity_update(self):
        self._lib.bugs_activity_update()

    def get_activity(self, max_n=4096):
        """Return activity table as dict of numpy arrays."""
        keys = np.zeros(max_n, dtype=np.uint32)
        acts = np.zeros(max_n, dtype=np.uint64)
        pops = np.zeros(max_n, dtype=np.uint32)
        cols = np.zeros(max_n, dtype=np.int32)
        n = self._lib.bugs_activity_get(
            keys.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
            acts.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            pops.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
            cols.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            max_n)
        return {'hash': keys[:n], 'activity': acts[:n],
                'pop_count': pops[:n], 'color': cols[:n]}

    def q_activity_deciles(self):
        """Return 9-element float array with activity deciles p10..p90."""
        out = np.zeros(9, dtype=np.float32)
        self._lib.bugs_q_activity_deciles(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        return out

    # ── Recipe export ─────────────────────────────────────────────────

    def export_recipe(self, descriptor, probes=None, colormode=0):
        """Export current initialization recipe to Runs/<date>_<descriptor>.bugs."""
        import json
        from datetime import datetime

        runs_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'Runs')
        os.makedirs(runs_dir, exist_ok=True)

        safe_desc = descriptor.replace(' ', '_')
        filename = f"{datetime.now().strftime('%Y-%m-%d')}_{safe_desc}.bugs"
        filepath = os.path.join(runs_dir, filename)

        recipe = {
            'version': 1,
            'created': datetime.now().isoformat(timespec='seconds'),
            'descriptor': descriptor,
            'N': self._N,
            'metaparams_init': dict(self._init_metaparams),
            'metaparams_final': {k: getattr(self, k) for k in self._DEFAULTS},
            'initialization': dict(self._state_params),
            'display': {
                'colormode': colormode,
                'probes': probes or {},
            },
        }

        with open(filepath, 'w') as f:
            json.dump(recipe, f, indent=2)
        return filepath

    @property
    def N(self):
        return self._N

    @property
    def cell_px(self):
        return self._lib.bugs_get_cell_px()


# ── Recipe import ─────────────────────────────────────────────────────

def import_run(filepath=None, recipe='init', lib_path=None):
    """Load a .bugs recipe file and return (sim, display_kwargs).

    If called with no arguments, lists available recipes in Runs/.
    """
    import json
    from pathlib import Path

    if filepath is None:
        runs_dir = Path(__file__).resolve().parent.parent / 'Runs'
        if not runs_dir.is_dir():
            print("No Runs/ directory found.")
            return []
        recipes = sorted(runs_dir.glob('*.bugs'))
        if not recipes:
            print("No .bugs files in Runs/.")
            return []
        for r in recipes:
            print(r.name)
        return [str(r) for r in recipes]

    with open(filepath) as f:
        data = json.load(f)

    mp = data['metaparams_init'] if recipe == 'init' else data['metaparams_final']

    sim = Bugs(lib_path=lib_path)
    sim.init(data['N'], **mp)

    init_raw = data.get('initialization', {})
    sim.state(**init_raw)

    disp = data.get('display', {})
    display_kwargs = {}
    if disp.get('colormode', 0) != 0:
        display_kwargs['colormode'] = disp['colormode']
    if disp.get('probes'):
        display_kwargs['probes'] = disp['probes']

    return sim, display_kwargs
