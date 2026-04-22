"""
bugs_py.py — Python ctypes wrapper for the Bugs C library.

Bugs model (Packard Bugs, Bedau & Packard 1991)
----------------------------------------------
Agents live on an N×N periodic grid with a float food field F(x) ∈ [0, 1].
Each bug carries 512 movement genes indexed by a 9-bit neighborhood
pattern (3×3 Moore neighborhood, visual reading order, y increases upward)
and a 9-entry *egenome* of per-position food thresholds θ_p:

    bit 0 : F(x-1, y+1) > θ_NW    (NW)
    bit 1 : F(x,   y+1) > θ_N     (N)
    bit 2 : F(x+1, y+1) > θ_NE    (NE)
    bit 3 : F(x-1, y  ) > θ_W     (W)
    bit 4 : F(x,   y  ) > θ_C     (C / self)
    bit 5 : F(x+1, y  ) > θ_E     (E)
    bit 6 : F(x-1, y-1) > θ_SW    (SW)
    bit 7 : F(x,   y-1) > θ_S     (S)
    bit 8 : F(x+1, y-1) > θ_SE    (SE)

Each gene encodes one of 120 moves: 8 directions × 15 magnitudes.
At birth, the child's egenome is the parent's with per-entry Gaussian
drift of width `mu_egenome` (clipped to [0, 1]). The egenome init vector
is API-only; typical starting regimes via the helpers
`egenome_center_only`, `egenome_constant`, `egenome_random`.
"""

import ctypes
import os

import numpy as np


NBHD       = 'moore'
NBHD_BITS  = 9
N_GENES    = 1 << NBHD_BITS   # 512 entries, one per 9-bit Moore pattern
MAG_MAX    = 15
N_DIRS     = 8
EGENOME_N  = 9   # one food_threshold per Moore-neighborhood position


def egenome_center_only(value=0.5):
    """Egenome with only the center (C / self) entry set.

    The bug can only perceive its own cell. Useful as the "minimal
    perception" baseline."""
    v = np.zeros(EGENOME_N, dtype=np.float32)
    v[4] = float(value)                          # center index in [NW,N,NE,W,C,E,SW,S,SE]
    return v


def egenome_constant(value=0.1):
    """Egenome with the same threshold θ on every position.

    `egenome_constant(0.1)` reproduces the historical scalar
    food_threshold=0.1 behaviour."""
    return np.full(EGENOME_N, float(value), dtype=np.float32)


def egenome_random(rng=None):
    """Egenome with each entry drawn i.i.d. uniform from [0, 1]."""
    if rng is None:
        rng = np.random.default_rng()
    return rng.random(EGENOME_N).astype(np.float32)

# Repo root (parent of Bugs/) — PNG templates live under CocoaBugs/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Built-in food-source PNG templates (from the original Obj-C plugin resources).
_FOOD_TEMPLATES = {
    'stripes':      'CocoaBugs/Stripes.png',
    'r-pentomino':  'CocoaBugs/R-pentomino.png',
    'big_box':      'CocoaBugs/Big box.png',
    '3x3_boxes':    'CocoaBugs/3x3 boxes.png',
    'empty_boxes':  'CocoaBugs/Empty boxes.png',
}


def food_templates():
    """Return {name: absolute_path} for all built-in food-source PNG templates."""
    return {n: os.path.join(_REPO_ROOT, p) for n, p in _FOOD_TEMPLATES.items()}


def _load_food_png(path_or_name, N):
    """Load a PNG into an (N, N) float32 brightness array in [0, 1].

    `path_or_name` is either a built-in template name (see food_templates()),
    an absolute filesystem path, or a path relative to the repo root.
    """
    from PIL import Image
    if path_or_name in _FOOD_TEMPLATES:
        path = os.path.join(_REPO_ROOT, _FOOD_TEMPLATES[path_or_name])
    elif os.path.isabs(path_or_name):
        path = path_or_name
    else:
        path = os.path.join(_REPO_ROOT, path_or_name)
    img = Image.open(path).convert('L').resize((N, N), Image.NEAREST)
    return (np.asarray(img, dtype=np.float32) / 255.0)


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
        mu_egenome=0.0,
        gdiff=0,
        move_range=15,
    )

    # Non-scalar metaparam with its own init-time kwarg (see state()).
    # Kept out of _DEFAULTS because _DEFAULTS drives the scalar
    # setter/getter loop and auto-generated updaters.
    _EGENOME_INIT_DEFAULT = np.full(EGENOME_N, 0.1, dtype=np.float32)

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
                     "mu_egenome"):
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
        L.bugs_set_move_range.argtypes       = [ctypes.c_int]
        L.bugs_set_move_range.restype        = None
        L.bugs_get_move_range.argtypes       = []
        L.bugs_get_move_range.restype        = ctypes.c_int

        # Egenome init vector and population stats
        L.bugs_set_egenome_init.argtypes     = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_set_egenome_init.restype      = None
        L.bugs_get_egenome_init.argtypes     = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_get_egenome_init.restype      = None
        L.bugs_egenome_stats.argtypes        = [ctypes.POINTER(ctypes.c_float),
                                                ctypes.POINTER(ctypes.c_float)]
        L.bugs_egenome_stats.restype         = None

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

        # G-activity probe (per whole-genome content hash; C symbol
        # names retain their historical "activity" spelling)
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

        # Gq-activity deciles
        L.bugs_q_activity_deciles.argtypes   = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_q_activity_deciles.restype    = None

        # g-activity probe (per (input nbhd, output move) pair)
        L.bugs_g_activity_update.argtypes    = []
        L.bugs_g_activity_update.restype     = None
        L.bugs_g_activity_render_col.argtypes = [ctypes.POINTER(ctypes.c_int32),
                                                 ctypes.c_int]
        L.bugs_g_activity_render_col.restype = None
        L.bugs_g_activity_get.argtypes       = [
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_int]
        L.bugs_g_activity_get.restype        = ctypes.c_int
        L.bugs_set_g_act_ymax.argtypes       = [ctypes.c_int]
        L.bugs_set_g_act_ymax.restype        = None
        L.bugs_get_g_act_ymax.argtypes       = []
        L.bugs_get_g_act_ymax.restype        = ctypes.c_int

        # gq-activity deciles
        L.bugs_gq_activity_deciles.argtypes  = [ctypes.POINTER(ctypes.c_float)]
        L.bugs_gq_activity_deciles.restype   = None

        # bug-coloring: per-LUT-index 31x31 move histogram
        L.bugs_bug_coloring_hist.argtypes    = [ctypes.c_int,
                                                ctypes.POINTER(ctypes.c_int32)]
        L.bugs_bug_coloring_hist.restype     = None

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
        # Non-scalar metaparam: egenome_init (length-9 vector, API-only)
        egenome_init = kwargs.pop('egenome_init', self._EGENOME_INIT_DEFAULT)
        self.set_egenome_init(egenome_init)
        if kwargs:
            raise TypeError(f"unknown init kwargs: {sorted(kwargs)}")
        self._state_params = {}
        self._init_metaparams = {k: getattr(self, k) for k in self._DEFAULTS}
        self._init_metaparams['egenome_init'] = self.get_egenome_init().tolist()

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
    update_mu_egenome        = _make_updater("mu_egenome")
    update_gdiff             = _make_updater("gdiff", is_int=True)
    update_move_range        = _make_updater("move_range", is_int=True)
    del _make_updater

    def update_G_act_ymax(self, y):
        self._lib.bugs_set_act_ymax(int(y))

    def update_g_act_ymax(self, y):
        self._lib.bugs_set_g_act_ymax(int(y))

    # ── Params export ─────────────────────────────────────────────────

    def params(self):
        """Return current metaparameters as a dict suitable for init(**d)."""
        p = dict(N=self._N, **{k: getattr(self, k) for k in self._DEFAULTS})
        p['egenome_init'] = self.get_egenome_init().tolist()
        return p

    def params_str(self):
        """Return a copy-pasteable sim.init(...) call with defaults annotated."""
        p = self.params()
        default_egenome = self._EGENOME_INIT_DEFAULT.tolist()
        lines = ["sim.init("]
        for k, v in p.items():
            val = repr(v)
            if k in self._DEFAULTS and v != self._DEFAULTS[k]:
                lines.append(f"    {k}={val},   # default: {self._DEFAULTS[k]!r}")
            elif k == 'egenome_init' and list(v) != default_egenome:
                lines.append(f"    {k}={val},   # default: {default_egenome!r}")
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

    def set_egenome_init(self, v):
        """Set the egenome initialization vector (length 9, entries clipped
        to [0, 1]). Affects bugs created by subsequent seeding only."""
        arr = np.ascontiguousarray(np.asarray(v, dtype=np.float32).ravel())
        if arr.size != EGENOME_N:
            raise ValueError(f"egenome_init must have {EGENOME_N} entries, got {arr.size}")
        self._lib.bugs_set_egenome_init(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        self._egenome_init = arr.copy()

    def get_egenome_init(self):
        """Return current egenome initialization vector as a (9,) float32."""
        out = np.zeros(EGENOME_N, dtype=np.float32)
        self._lib.bugs_get_egenome_init(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        return out

    def egenome_stats(self):
        """Return (mean, std) of the egenome over live bugs, each (9,) float32.
        Ordering is [NW, N, NE, W, C, E, SW, S, SE]."""
        mean = np.zeros(EGENOME_N, dtype=np.float32)
        std  = np.zeros(EGENOME_N, dtype=np.float32)
        self._lib.bugs_egenome_stats(
            mean.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            std.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        return mean, std

    def state(self, food_source='uniform', food_source_value=1.0,
              food_source_thresh=0.5, brightness=None,
              template=None, seed_density=0.1, egenome_init=None):
        """Initialize food field and bug population from parameters.

        food_source:
          'uniform'    — uniform F_source = food_source_value everywhere
          'brightness' — load `brightness` (np.ndarray, or str path / template
                         name) as grayscale in [0,1]; threshold at
                         food_source_thresh (pixels below → food, else 0)
          'template'   — shorthand: load built-in PNG template by name (see
                         Bugs.food_templates()), threshold at food_source_thresh
          'custom'     — use `brightness` directly as F_source (no threshold)

        egenome_init: length-9 vector of per-position food thresholds in
          [0, 1]; order [NW, N, NE, W, C, E, SW, S, SE]. If None, uses the
          current C-side value (class default: 0.1 on every position).
          See helpers egenome_center_only / egenome_constant / egenome_random.
        """
        if egenome_init is not None:
            self.set_egenome_init(egenome_init)
        self._state_params = {}
        if food_source == 'template':
            if template is None:
                raise ValueError(
                    "food_source='template' requires template=<name> "
                    f"(one of {list(_FOOD_TEMPLATES)})")
            img = _load_food_png(template, self._N)
            self.set_food_source_from_brightness(img, food_source_thresh)
            self._state_params['food_source']        = 'template'
            self._state_params['template']           = template
            self._state_params['food_source_thresh'] = float(food_source_thresh)
        elif food_source == 'brightness':
            if brightness is None:
                raise ValueError("food_source='brightness' requires brightness=")
            if isinstance(brightness, str):
                img = _load_food_png(brightness, self._N)
                self.set_food_source_from_brightness(img, food_source_thresh)
                self._state_params['brightness'] = brightness
            else:
                self.set_food_source_from_brightness(brightness, food_source_thresh)
                self._state_params['brightness'] = np.ascontiguousarray(
                    np.asarray(brightness, dtype=np.float32))
        elif food_source == 'custom':
            if brightness is None:
                raise ValueError("food_source='custom' requires src array")
            self.set_food_source(brightness)
            self._state_params['brightness'] = np.ascontiguousarray(
                np.asarray(brightness, dtype=np.float32))
        else:
            self.set_food_source_uniform(food_source_value)
        self.exterminate()
        self.seed_with_density(seed_density)
        # Log whatever egenome_init is live on the C side into the recipe
        # state_params, regardless of whether the caller passed it here or
        # set it earlier via sim.set_egenome_init().
        self._state_params['egenome_init'] = self.get_egenome_init().tolist()

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

    # ── G-activity probe (per whole-genome content hash) ──────────────

    def G_activity_update(self):
        self._lib.bugs_activity_update()

    def get_G_activity(self, max_n=4096):
        """Return G-activity table as dict of numpy arrays.
        Keys are FNV-1a hashes of the 512-gene genome bytes."""
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

    def Gq_activity_deciles(self):
        """Return 9-element float array with G-activity deciles p10..p90."""
        out = np.zeros(9, dtype=np.float32)
        self._lib.bugs_q_activity_deciles(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        return out

    # ── g-activity probe (per (input, output) LUT-slot pair) ──────────

    def g_activity_update(self):
        self._lib.bugs_g_activity_update()

    def get_g_activity(self, max_n=8192):
        """Return g-activity table as dict of numpy arrays.
        Keys pack (nbhd, dx, dy) — see bugs.h for layout."""
        keys = np.zeros(max_n, dtype=np.uint32)
        acts = np.zeros(max_n, dtype=np.uint64)
        pops = np.zeros(max_n, dtype=np.uint32)
        cols = np.zeros(max_n, dtype=np.int32)
        n = self._lib.bugs_g_activity_get(
            keys.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
            acts.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            pops.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
            cols.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            max_n)
        return {'key': keys[:n], 'activity': acts[:n],
                'pop_count': pops[:n], 'color': cols[:n]}

    def gq_activity_deciles(self):
        """Return 9-element float array with g-activity deciles p10..p90."""
        out = np.zeros(9, dtype=np.float32)
        self._lib.bugs_gq_activity_deciles(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        return out

    def bug_coloring_hist(self, gene_idx):
        """Compute a 31x31 histogram of per-bug (dx, dy) outputs at LUT
        index `gene_idx`. Row i → dy = i - 15, col j → dx = j - 15."""
        out = np.zeros((31, 31), dtype=np.int32)
        self._lib.bugs_bug_coloring_hist(
            int(gene_idx),
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)))
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

        mp_final = {k: getattr(self, k) for k in self._DEFAULTS}
        mp_final['egenome_init'] = self.get_egenome_init().tolist()

        # Serialize any ndarray state_params (e.g. brightness for
        # food_source='brightness'/'custom') as .npy sidecars next to the
        # .bugs file, and replace the entry with a `<key>_npy: filename`
        # pointer. import_run resolves the pointer back into an ndarray.
        init_params = dict(self._state_params)
        basename = filename[:-len('.bugs')]
        for key in list(init_params):
            val = init_params[key]
            if isinstance(val, np.ndarray):
                sidecar_name = f"{basename}.{key}.npy"
                np.save(os.path.join(runs_dir, sidecar_name), val)
                del init_params[key]
                init_params[f"{key}_npy"] = sidecar_name

        recipe = {
            'version': 3,
            'nbhd': NBHD,                     # 'moore' (9-bit) or 'von_neumann' (5-bit)
            'n_genes': N_GENES,
            'created': datetime.now().isoformat(timespec='seconds'),
            'descriptor': descriptor,
            'N': self._N,
            'metaparams_init': dict(self._init_metaparams),
            'metaparams_final': mp_final,
            'initialization': init_params,
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

def import_run(filepath=None, recipe='final', lib_path=None):
    """Load a .bugs recipe file and return (sim, display_kwargs).

    `recipe='final'` (default) starts the new sim from the metaparams that
    were live at the moment of export — i.e. the explored state the user
    chose to preserve. `recipe='init'` starts from the metaparams the
    original run itself was initialized with (the t=0 snapshot). Either way,
    the seed population is re-generated from `initialization`, so full
    trajectory reproducibility is approximate; the recipe captures the
    parameter regime, not the history of slider drags.

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

    # Neighborhood-compatibility check.
    # v1 recipes (pre-Moore) have no 'nbhd' field; treat as legacy von_neumann.
    recipe_nbhd = data.get('nbhd', 'von_neumann')
    if recipe_nbhd != NBHD:
        raise ValueError(
            f"recipe '{filepath}' was written for nbhd='{recipe_nbhd}' "
            f"(n_genes={data.get('n_genes', 32)}) but the current build is "
            f"nbhd='{NBHD}' (n_genes={N_GENES}). Recipes are not transferable "
            f"across neighborhood topologies — genome structure differs.")

    mp_init  = dict(data['metaparams_init'])
    mp_final = dict(data['metaparams_final'])

    # Legacy migration: pre-v3 recipes stored a scalar `food_threshold`
    # rather than a per-position `egenome_init` vector. Translate the
    # scalar into a constant 9-vector (the historical behaviour) and drop
    # the old key. mu_egenome defaults to 0.0 (no drift).
    for mp_dict in (mp_init, mp_final):
        if 'food_threshold' in mp_dict:
            ft = float(mp_dict.pop('food_threshold'))
            mp_dict.setdefault('egenome_init', [ft] * EGENOME_N)
            mp_dict.setdefault('mu_egenome', 0.0)

    mp = mp_init if recipe == 'init' else mp_final

    # Show the init→final delta so the user knows which regime they're
    # loading. Only show keys that actually changed during exploration.
    deltas = {k: (mp_init.get(k), mp_final.get(k))
              for k in set(mp_init) | set(mp_final)
              if mp_init.get(k) != mp_final.get(k)}
    if deltas:
        arrow = "  (using final)" if recipe == 'final' else "  (using init)"
        print(f"recipe {Path(filepath).name}: explored params{arrow}")
        for k, (vi, vf) in sorted(deltas.items()):
            print(f"    {k:20s}  init={vi!r}  →  final={vf!r}")

    sim = Bugs(lib_path=lib_path)
    sim.init(data['N'], **mp)

    init_raw = data.get('initialization', {})
    # Resolve `<key>_npy: filename` sidecar pointers back into ndarrays,
    # loaded from the same directory as the recipe file.
    recipe_dir = Path(filepath).parent
    init_kwargs = {}
    for key, val in init_raw.items():
        if key.endswith('_npy') and isinstance(val, str):
            init_kwargs[key[:-len('_npy')]] = np.load(recipe_dir / val)
        else:
            init_kwargs[key] = val
    sim.state(**init_kwargs)

    disp = data.get('display', {})
    display_kwargs = {}
    if disp.get('colormode', 0) != 0:
        display_kwargs['colormode'] = disp['colormode']
    if disp.get('probes'):
        # Migrate legacy probe keys: 'activity' → 'G-activity',
        # 'q_activity' → 'Gq-activity'. (Old recipes predate the
        # G/g split introduced 2026-04.)
        probes = dict(disp['probes'])
        if 'activity' in probes:
            probes['G-activity'] = probes.pop('activity')
        if 'q_activity' in probes:
            probes['Gq-activity'] = probes.pop('q_activity')
        display_kwargs['probes'] = probes

    return sim, display_kwargs
