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
        L.bugs_get_egenome_all.argtypes      = [ctypes.POINTER(ctypes.c_float),
                                                ctypes.c_int]
        L.bugs_get_egenome_all.restype       = ctypes.c_int
        L.bugs_get_ages.argtypes             = [ctypes.POINTER(ctypes.c_int32),
                                                ctypes.c_int]
        L.bugs_get_ages.restype              = ctypes.c_int

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
        L.bugs_get_food_eaten_last.argtypes  = []
        L.bugs_get_food_eaten_last.restype   = ctypes.c_float
        L.bugs_count_distinct_genomes.argtypes  = []
        L.bugs_count_distinct_genomes.restype   = ctypes.c_int
        L.bugs_count_distinct_io_pairs.argtypes = []
        L.bugs_count_distinct_io_pairs.restype  = ctypes.c_int
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

    def get_egenome(self):
        """Return the current egenome of every live bug as a (pop, 9) float32
        ndarray. Column order is [NW, N, NE, W, C, E, SW, S, SE]."""
        pop = self.get_population()
        out = np.zeros((pop, EGENOME_N), dtype=np.float32)
        if pop == 0:
            return out
        n = self._lib.bugs_get_egenome_all(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), pop)
        return out[:n]

    def get_ages(self):
        """Return ages of every live bug as a (pop,) int32 ndarray,
        in alive-order (the same order as get_egenome rows)."""
        pop = self.get_population()
        out = np.zeros(pop, dtype=np.int32)
        if pop == 0:
            return out
        n = self._lib.bugs_get_ages(
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), pop)
        return out[:n]

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

    def get_food_eaten_last(self):
        """Total food eaten by all bugs during the most recent bugs_step().
        Zeroed at the start of each step."""
        return float(self._lib.bugs_get_food_eaten_last())

    def count_distinct_genomes(self):
        """# distinct genome_hash values across live bugs."""
        return int(self._lib.bugs_count_distinct_genomes())

    def count_distinct_io_pairs(self):
        """# distinct (current-nbhd, dx, dy) input/output pairs across live bugs."""
        return int(self._lib.bugs_count_distinct_io_pairs())

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


# ── Diagnostics ──────────────────────────────────────────────────────

def plot_food_power_spectrum(sim, num_frames=1, step_each=1,
                             subtract_mean=True, k_min=2,
                             show=True, figsize=(13, 4)):
    """Plot the 2D power spectrum of the food field and horizontal/vertical
    + diagonal cuts, as a symmetry diagnostic.

    For an isotropic process the 2D power spectrum should look (statistically)
    radially symmetric. A systematic excess along the kx-axis vs the ky-axis
    — or vice versa — is a red flag: something in the simulation prefers one
    cardinal direction over the other. Evolution *may* break symmetry, but
    the direction in which it breaks should be random across runs.

    The integrated (A−B)/(A+B) diagonal-total asymmetry is blind to shape
    mismatches at equal total power, and is noise-dominated by the huge
    low-k bins near DC. This function therefore:

      * applies a near-DC mask (`k_min`) that zeros out |k| < k_min bins on
        all four cuts before any summing — killing the low-k pileup;
      * reports a **bin-by-bin** diagonal metric as the headline number:
        `diag_asym = Σ|A_i − B_i| / Σ(A_i + B_i)` — sensitive to per-bin
        differences regardless of total power match;
      * also reports a **shape** metric `diag_shape` = total-variation
        distance between the two normalized diagonals, and a magnitude
        `asymmetry_diag = |A−B|/(A+B)` (the unsigned version of the old
        total-imbalance metric).

    Parameters
    ----------
    sim : Bugs
    num_frames : int
        Number of FFT frames to average. Averaging reduces noise in the
        per-frame spectrum; 20–100 frames is usually enough to see a bias.
    step_each : int
        Sim ticks between captured frames. With num_frames=1 no stepping
        happens.
    subtract_mean : bool
        Subtract F.mean() before FFT to kill the DC spike at (0,0), which
        otherwise dominates log-display.
    k_min : int
        Near-DC mask radius (in bin-index units from DC, applied along
        each cut). Bins with |k| < k_min are zeroed before summing and
        NaN'd in the cuts plot. k_min=1 masks only DC itself; k_min=2
        also kills the ±1 neighbors that usually dominate the sum; larger
        values suppress progressively more of the low-k shoulder.
        Default 2.
    show : bool
        If True (default), the figure is drawn inline by the Jupyter
        auto-display mechanism. If False, the figure is detached from
        pyplot's manager (plt.close(fig)) so it won't auto-show — useful
        in a loop that accumulates many runs. The returned fig is still
        live and can be redisplayed later with
        `from IPython.display import display; display(fig)`
        (matplotlib's `fig.show()` is a no-op under the inline backend).
    figsize : tuple

    Returns
    -------
    (fig, info) : matplotlib Figure, dict of symmetry metrics.
        info keys:
          'P_horiz_axis', 'P_vert_axis', 'P_ne_sw', 'P_nw_se' — masked sums
            along the four cuts;
          'asymmetry'      — signed (V−H)/(V+H) H-V imbalance;
          'asymmetry_diag' — unsigned |A−B|/(A+B) diagonal-total imbalance;
          'diag_asym'      — bin-by-bin Σ|A_i−B_i|/(A+B) (headline);
          'diag_shape'     — TV distance between normalized diagonals ∈[0,1];
          'k_min'          — the near-DC mask radius actually used;
          'P_mean_2d'      — the averaged fftshifted power spectrum.
    """
    import matplotlib.pyplot as plt

    N = sim.N
    Nc = N // 2  # index of zero frequency after fftshift

    P_acc = np.zeros((N, N), dtype=np.float64)
    for f in range(num_frames):
        if f > 0:
            for _ in range(step_each):
                sim.step()
        F = sim.get_food_field().reshape(N, N).astype(np.float64)
        if subtract_mean:
            F = F - F.mean()
        Fhat = np.fft.fft2(F)
        P_acc += np.abs(Fhat) ** 2
    P_acc /= num_frames
    P = np.fft.fftshift(P_acc)

    # Near-DC mask helper: zero bins with |i − dc_idx| < k_min on a 1D cut.
    # Used before summing. Plot version (below) substitutes NaN for zero.
    idx = np.arange(N)
    def _mask_sum(arr, dc_idx):
        a = arr.astype(float).copy()
        a[np.abs(idx - dc_idx) < k_min] = 0.0
        return a
    def _mask_plot(arr, dc_idx):
        a = arr.astype(float).copy()
        a[np.abs(idx - dc_idx) < k_min] = np.nan
        return a

    # Axis cuts (ky=0 and kx=0 lines).
    horiz_axis = _mask_sum(P[Nc, :], Nc)      # ky=0, kx varying
    vert_axis  = _mask_sum(P[:, Nc], Nc)      # kx=0, ky varying
    P_h = float(horiz_axis.sum())
    P_v = float(vert_axis.sum())
    denom = P_v + P_h
    asym = (P_v - P_h) / denom if denom > 0 else 0.0

    # Diagonal cuts: NE-SW is P[i, i], NW-SE is P[i, N-1-i]. For even N the
    # NW-SE line is offset 1/2 bin from DC; the index-based |i−Nc| mask is
    # still the right way to kill the low-k neighborhood.
    ne_sw_axis = _mask_sum(np.diag(P),             Nc)
    nw_se_axis = _mask_sum(np.diag(np.fliplr(P)),  Nc)
    P_ne_sw = float(ne_sw_axis.sum())
    P_nw_se = float(nw_se_axis.sum())
    denom_d = P_ne_sw + P_nw_se

    # Three diagonal metrics (all unsigned):
    if denom_d > 0:
        asym_diag = abs(P_ne_sw - P_nw_se) / denom_d     # total imbalance
        diag_asym = float(np.abs(ne_sw_axis - nw_se_axis).sum()) / denom_d
        pA = ne_sw_axis / P_ne_sw if P_ne_sw > 0 else np.zeros_like(ne_sw_axis)
        pB = nw_se_axis / P_nw_se if P_nw_se > 0 else np.zeros_like(nw_se_axis)
        diag_shape = 0.5 * float(np.abs(pA - pB).sum())  # TV distance
    else:
        asym_diag = diag_asym = diag_shape = 0.0

    fig, axes = plt.subplots(1, 3, figsize=figsize)
    F_disp = sim.get_food_field().reshape(N, N)
    axes[0].imshow(F_disp, origin='lower', cmap='Greens', vmin=0, vmax=1)
    axes[0].set_title(f'food field  (t={sim.get_step()})')
    axes[0].set_xlabel('x'); axes[0].set_ylabel('y')

    logP = np.log10(P + 1e-12)
    axes[1].imshow(logP, origin='lower', cmap='magma',
                   extent=[-Nc, Nc, -Nc, Nc])
    axes[1].set_title(f'log$_{{10}}$ |F̂|²  (avg of {num_frames} frames)')
    axes[1].set_xlabel('kx'); axes[1].set_ylabel('ky')
    axes[1].axhline(0, color='cyan', lw=0.5, alpha=0.4)
    axes[1].axvline(0, color='cyan', lw=0.5, alpha=0.4)
    # Mark both diagonals too so the eye can match plot lines to cuts.
    axes[1].plot([-Nc, Nc], [-Nc, Nc], color='cyan',
                 lw=0.5, alpha=0.4, linestyle='--')
    axes[1].plot([-Nc, Nc], [Nc, -Nc], color='cyan',
                 lw=0.5, alpha=0.4, linestyle='--')

    ks = np.arange(-Nc, N - Nc)
    h_plot     = _mask_plot(P[Nc, :],              Nc)
    v_plot     = _mask_plot(P[:, Nc],              Nc)
    ne_sw_plot = _mask_plot(np.diag(P),            Nc)
    nw_se_plot = _mask_plot(np.diag(np.fliplr(P)), Nc)

    axes[2].semilogy(ks, h_plot,     label=f'ky=0  (H)   Σ={P_h:.2e}')
    axes[2].semilogy(ks, v_plot,     label=f'kx=0  (V)   Σ={P_v:.2e}')
    axes[2].semilogy(ks, ne_sw_plot, linestyle='--',
                     label=f'ky=kx (NE-SW) Σ={P_ne_sw:.2e}')
    axes[2].semilogy(ks, nw_se_plot, linestyle='--',
                     label=f'ky=-kx (NW-SE) Σ={P_nw_se:.2e}')
    axes[2].set_title(f'H-V asym = {asym:+.3f}    '
                      f'diag asym = {diag_asym:.3f}')
    axes[2].set_xlabel('k'); axes[2].set_ylabel('|F̂|²')
    axes[2].legend(fontsize=7, loc='lower center', ncol=2)
    axes[2].grid(alpha=0.3)

    fig.tight_layout()
    if not show:
        plt.close(fig)
    return fig, {
        'P_horiz_axis':   P_h,
        'P_vert_axis':    P_v,
        'P_ne_sw':        P_ne_sw,
        'P_nw_se':        P_nw_se,
        'asymmetry':      asym,
        'asymmetry_diag': asym_diag,
        'diag_asym':      diag_asym,
        'diag_shape':     diag_shape,
        'k_min':          k_min,
        'P_mean_2d':      P,
    }


# Direction index convention matches bugs.c random_gene(): dir = (quad<<1)|diag.
#   0:E, 1:NE, 2:N, 3:NW, 4:W, 5:SW, 6:S, 7:SE
_DIR_NAMES  = ['E', 'NE', 'N', 'NW', 'W', 'SW', 'S', 'SE']
_DIR_ANGLES = np.deg2rad([0, 45, 90, 135, 180, 225, 270, 315])


def _dxdy_to_dir(sdx, sdy):
    """Vectorized (sign(dx), sign(dy)) -> direction bin in [0..7], -1 if (0,0)."""
    idx = np.full(sdx.shape, -1, dtype=np.int32)
    idx[(sdx == +1) & (sdy ==  0)] = 0
    idx[(sdx == +1) & (sdy == +1)] = 1
    idx[(sdx ==  0) & (sdy == +1)] = 2
    idx[(sdx == -1) & (sdy == +1)] = 3
    idx[(sdx == -1) & (sdy ==  0)] = 4
    idx[(sdx == -1) & (sdy == -1)] = 5
    idx[(sdx ==  0) & (sdy == -1)] = 6
    idx[(sdx == +1) & (sdy == -1)] = 7
    return idx


def plot_move_direction_histogram(sim, num_frames=1, step_each=1,
                                  show=True, figsize=(11, 4)):
    """Aggregate the direction of each live bug's gene-output move into an
    8-bin histogram, accumulated over num_frames.

    For an isotropic population the 8 bins should be statistically equal.
    Systematic cardinal imbalance (E+W vs N+S) or diagonal imbalance
    (NE+SW vs NW+SE) is a sign of axis-asymmetry in the update rule itself,
    independent of the food field.

    Data is drawn from the g-activity hash table, which records, per live
    bug per call, the (nbhd, gene-dx, gene-dy) pair currently being used.
    The function advances `sim` by (num_frames-1)*step_each ticks.

    Returns
    -------
    (fig, info) : Figure, dict
        info keys: 'hist' (int64[8]), 'axis_asym' ((N+S−E−W)/total, in
        [-1,1]), 'diag_asym' ((NE+SW−NW−SE)/total).
    """
    import matplotlib.pyplot as plt

    hist = np.zeros(8, dtype=np.int64)
    for f in range(num_frames):
        if f > 0:
            for _ in range(step_each):
                sim.step()
        sim.g_activity_update()
        d = sim.get_g_activity(max_n=200_000)
        keys = d['key']; pops = d['pop_count']
        if len(keys) == 0:
            continue
        # Only count buckets with pop_count > 0 (live usage this tick).
        alive = pops > 0
        if not alive.any():
            continue
        k = keys[alive]; p = pops[alive]
        dx = ((k >> 8) & 0xFF).astype(np.int32) - 15
        dy = ( k       & 0xFF).astype(np.int32) - 15
        idx = _dxdy_to_dir(np.sign(dx), np.sign(dy))
        ok = idx >= 0
        if ok.any():
            hist += np.bincount(idx[ok], weights=p[ok].astype(np.int64),
                                minlength=8).astype(np.int64)

    total = int(hist.sum())
    E, NE, N, NW, W, SW, S, SE = [int(h) for h in hist]
    axis_den = N + S + E + W
    diag_den = NE + SW + NW + SE
    axis_asym = ((N + S) - (E + W)) / axis_den if axis_den > 0 else 0.0
    diag_asym = ((NE + SW) - (NW + SE)) / diag_den if diag_den > 0 else 0.0

    fig, axes = plt.subplots(
        1, 2, figsize=figsize,
        subplot_kw={'projection': None})  # set per-axis below
    # Left: bar chart ordered N, NE, E, SE, S, SW, W, NW (clockwise compass)
    order = [2, 1, 0, 7, 6, 5, 4, 3]
    names = [_DIR_NAMES[i] for i in order]
    axes[0].bar(range(8), hist[order],
                color=['#4b8bbe'] * 8, edgecolor='k')
    if total > 0:
        axes[0].axhline(total / 8, color='r', lw=1, ls='--',
                        label=f'uniform ({total/8:.0f})')
        axes[0].legend(fontsize=8, loc='lower right')
    axes[0].set_xticks(range(8)); axes[0].set_xticklabels(names)
    axes[0].set_ylabel('Σ bug·ticks')
    axes[0].set_title(f'move-direction counts (n={total})')

    # Right: polar bar chart — makes axis/diag symmetry visually obvious.
    axes[1].remove()
    axp = fig.add_subplot(1, 2, 2, projection='polar')
    width = np.deg2rad(45)
    axp.bar(_DIR_ANGLES, hist, width=width, bottom=0.0,
            color='#4b8bbe', edgecolor='k', alpha=0.8, align='center')
    axp.set_theta_zero_location('E')
    axp.set_theta_direction(1)  # counter-clockwise (math convention)
    axp.set_xticks(_DIR_ANGLES)
    axp.set_xticklabels(_DIR_NAMES)
    axp.set_title(f'axis asym={axis_asym:+.3f}  '
                  f'diag asym={diag_asym:+.3f}', fontsize=10)

    fig.tight_layout()
    if not show:
        plt.close(fig)
    return fig, {
        'hist':      hist,
        'axis_asym': axis_asym,
        'diag_asym': diag_asym,
        'total':     total,
    }


# Egenome position indexing:  [NW, N, NE, W, C, E, SW, S, SE] → 0..8
_EG_ORBIT_EDGES   = [1, 3, 5, 7]   # N, W, E, S
_EG_ORBIT_CORNERS = [0, 2, 6, 8]   # NW, NE, SW, SE
_EG_POS_NAMES     = ['NW', 'N', 'NE', 'W', 'C', 'E', 'SW', 'S', 'SE']

# Matches the palette used by the egenome SDL probe (sdl_worker._EG_RGB).
_EG_PALETTE = [
    (0xFF, 0x44, 0x44), (0xFF, 0x99, 0x44), (0xFF, 0xDD, 0x44),
    (0xAA, 0xFF, 0x44), (0x44, 0xFF, 0x88), (0x44, 0xDD, 0xFF),
    (0x44, 0x88, 0xFF), (0xAA, 0x44, 0xFF), (0xFF, 0x44, 0xDD),
]


def plot_egenome(sim, eps=1e-3, bw_adjust=0.5, show=True, figsize=(11, 5)):
    """Plot the 9 per-position egenome distributions as overlaid KDE curves.

    Many simulations peg one or more egenome positions at 0 or 1 while
    others drift in the interior of [0, 1]. A naive KDE collapses those
    pegged distributions into tall narrow spikes that swamp the
    interior-only curves. This function separates boundary mass from
    interior mass: samples within `eps` of 0 or 1 are excluded from the
    KDE and reported as fractions in the legend instead. The plotted
    curves thus have usable dynamic range even when other positions are
    delta functions.

    Parameters
    ----------
    sim : Bugs
        A running simulation with a nonempty population.
    eps : float
        Half-width of the "boundary" zone around 0 and 1. Samples with
        value <= eps or >= 1-eps are counted as boundary mass rather
        than fed to the KDE.
    bw_adjust : float
        Scales seaborn's KDE bandwidth; smaller = sharper.
    show : bool
        If False, the figure is detached from pyplot so it won't display
        inline — useful in sweeps.
    figsize : tuple

    Returns
    -------
    (fig, info) : Figure, dict
        info is keyed by position name ('NW', 'N', ...) and each entry
        contains: 'p_lo' (fraction <= eps), 'p_hi' (fraction >= 1-eps),
        'p_interior', 'interior_n' (KDE sample count).
    """
    import matplotlib.pyplot as plt
    try:
        import seaborn as sns
    except ImportError as e:
        raise ImportError(
            "plot_egenome requires seaborn (pip install seaborn)") from e

    eg = sim.get_egenome()
    if eg.shape[0] == 0:
        raise RuntimeError("no alive bugs — nothing to plot")

    colors = [(r / 255., g / 255., b / 255.) for (r, g, b) in _EG_PALETTE]

    fig, ax = plt.subplots(figsize=figsize)
    info = {}
    for p in range(9):
        v = eg[:, p]
        at_lo = float((v <= eps).mean())
        at_hi = float((v >= 1.0 - eps).mean())
        interior = v[(v > eps) & (v < 1.0 - eps)]
        info[_EG_POS_NAMES[p]] = dict(
            p_lo=at_lo, p_hi=at_hi,
            p_interior=1.0 - at_lo - at_hi,
            interior_n=int(len(interior)))
        label = (f'{_EG_POS_NAMES[p]:<2}  '
                 f'0:{at_lo:.2f}  mid:{1-at_lo-at_hi:.2f}  1:{at_hi:.2f}')
        if len(interior) >= 5:
            sns.kdeplot(x=interior, ax=ax, color=colors[p],
                        alpha=0.35, linewidth=1.5, fill=True,
                        bw_adjust=bw_adjust, clip=(0.0, 1.0), label=label)
        else:
            # Not enough interior samples to fit a KDE — show a legend
            # entry so the boundary mass is still visible to the reader.
            ax.plot([], [], color=colors[p], label=label)

    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel('egenome threshold value')
    ax.set_ylabel('KDE density  (interior-only)')
    ax.set_title(f'egenome per-position distributions  '
                 f'pop={eg.shape[0]}  t={sim.get_step()}  (ε={eps})')
    # matplotlib fills legend entries column-major; reorder handles so
    # the 3x3 legend reads row-major as a compass rose: NW N NE / W C E / SW S SE.
    handles, labels = ax.get_legend_handles_labels()
    if len(handles) == 9:
        # row-major idx p = row*3 + col; column-major fill order picks cols first.
        perm = [0, 3, 6, 1, 4, 7, 2, 5, 8]
        handles = [handles[i] for i in perm]
        labels  = [labels[i]  for i in perm]
    ax.legend(handles, labels, fontsize=8, loc='upper center',
              ncol=3, framealpha=0.85)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    if not show:
        plt.close(fig)
    return fig, info


def plot_egenome_orbit_sweep(init, state, *, seeds, steps,
                             show=True, figsize=(12, 4)):
    """Multi-seed sweep of egenome per-position means at a fixed long-run step.

    Under an isotropic rule + food, the fitness landscape has D4 symmetry,
    so the population mean should respect three orbits: four edges
    {N, W, E, S}, four corners {NW, NE, SW, SE}, and center {C}. A single
    long-run seed can break symmetry via lineage dominance — the test is
    whether per-orbit spread averages to zero across many seeds, i.e.
    the 'winning' direction flips seed-to-seed.

    Parameters
    ----------
    init   : dict of kwargs for sim.init(**init)
    state  : dict of kwargs for sim.state(**state)
    seeds  : iterable of int seeds
    steps  : int, simulation steps per seed before reading egenome_stats

    Returns
    -------
    (fig, info) : Figure, dict
        info keys: 'means' (n_seeds,9), 'edge_spread' (n_seeds,) max−min
        within edges, 'corner_spread' (n_seeds,) max−min within corners,
        'across_mean' (9,), 'across_std' (9,).
    """
    import matplotlib.pyplot as plt

    seeds = list(seeds)
    n = len(seeds)
    means = np.zeros((n, EGENOME_N), dtype=np.float32)
    for i, k in enumerate(seeds):
        sim = Bugs()
        sim.init(**init)
        sim.set_seed(int(k))
        sim.state(**state)
        for _ in range(int(steps)):
            sim.step()
        m, _ = sim.egenome_stats()
        means[i] = m
        sim.free()

    edges   = means[:, _EG_ORBIT_EDGES]
    corners = means[:, _EG_ORBIT_CORNERS]
    edge_spread   = edges  .max(axis=1) - edges  .min(axis=1)
    corner_spread = corners.max(axis=1) - corners.min(axis=1)
    across_mean   = means.mean(axis=0)
    across_std    = means.std (axis=0)

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Left: parallel coordinates — one line per seed, across-seed mean overlaid
    ax = axes[0]
    xs = np.arange(EGENOME_N)
    for i in range(n):
        ax.plot(xs, means[i], marker='o', ms=4, alpha=0.55, lw=1)
    ax.errorbar(xs, across_mean, yerr=across_std, color='k', lw=2, ms=6,
                marker='s', capsize=4, label='across-seed mean ± std',
                zorder=10)
    ax.set_xticks(xs); ax.set_xticklabels(_EG_POS_NAMES)
    ax.set_xlabel('Moore position')
    ax.set_ylabel('egenome mean')
    ax.set_ylim(0, 1)
    ax.set_title(f'per-seed egenome means  (n={n} seeds, {steps} steps)')
    ax.legend(loc='best', fontsize=8)

    # Right: per-seed within-orbit spread
    ax = axes[1]
    ax.scatter(edge_spread, corner_spread, s=45, c='#4b8bbe', edgecolors='k')
    hi = max(float(edge_spread.max()), float(corner_spread.max()), 1e-3) * 1.1
    ax.plot([0, hi], [0, hi], 'k--', alpha=0.3, lw=1)
    ax.set_xlabel('edge spread  max−min of {N, W, E, S}')
    ax.set_ylabel('corner spread  max−min of {NW, NE, SW, SE}')
    ax.set_xlim(0, hi); ax.set_ylim(0, hi)
    ax.set_title('per-seed within-orbit spread')
    ax.set_aspect('equal')

    fig.tight_layout()
    if not show:
        plt.close(fig)
    return fig, {
        'means':         means,
        'edge_spread':   edge_spread,
        'corner_spread': corner_spread,
        'across_mean':   across_mean,
        'across_std':    across_std,
    }
