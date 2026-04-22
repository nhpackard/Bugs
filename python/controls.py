"""
controls.py — ipywidgets control panel + SDL2 display for Bugs.

Architecture
------------
SDL2 requires macOS's actual main thread (thread 0), which belongs to the
Jupyter kernel's event loop.  Running SDL2 in any other thread crashes the
kernel.  The fix: run SDL2 in a *subprocess* that has its own main thread.

  Main process (Jupyter kernel)
  ├── Jupyter event loop  →  ipywidgets callbacks fire here
  ├── Sim thread          →  sim.step() + sim.colorize() → shared memory
  ├── Reader thread       →  relays SDL worker stdout to terminal
  └── subprocess (sdl_worker.py)
      └── SDL2 main thread  →  reads shared memory, renders window

Pixel data flows via POSIX shared memory with no copying:
  sim.colorize(pixels_shm, …) writes directly into shared memory;
  the subprocess reads the same buffer.

Usage (Jupyter cell)
--------------------
    from python.controls import run_with_controls
    run_with_controls(sim)
    # Cell returns immediately; widgets appear below; SDL2 window opens.
    # Click Quit or press Q/Esc in the SDL2 window to stop.
    # Then call sim.free() in the next cell.
"""

import atexit
import ctypes
import os
import subprocess
import sys
import threading
import time

import ipywidgets as widgets
import matplotlib.pyplot as plt
import numpy as np
from IPython.display import display as ipy_display
from multiprocessing.shared_memory import SharedMemory


COLOR_MODES      = ["red-bugs", "genome-hash", "bug-food"]
_SLIDER_RESUME_S = 0.20
_WORKER          = os.path.join(os.path.dirname(__file__), "sdl_worker.py")

# ctrl_shm layout (5 × int32)
_QUIT, _CMODE, _STEP, _FPS10, _PAUSED = 0, 1, 2, 3, 4

# Probe strip-chart constants
PROBE_W = 1024
PROBE_H = 128

_AVAILABLE_PROBES = {
    'G-activity':  'G-activity: whole-genome content-hash strip chart',
    'Gq-activity': 'Gq-activity: G-activity deciles',
    'g-activity':  'g-activity: per (nbhd, move) LUT-slot strip chart',
    'gq-activity': 'gq-activity: g-activity deciles',
    'egenome':     'Egenome: 9 translucent position bands (mean ± std)',
    'ts':          'Scalar time-series (population, total food-in-bugs)',
    'coloring':    'Bug-coloring: per-LUT-index move distribution (3x3 template)',
}

# Egenome probe: 9 position bands, each with a (mean, std) pair stored
# as two PROBE_W-long float32 traces. Palette lives in sdl_worker.
_EG_N_POS = 9

# Bit labels for the 3x3 Moore-neighborhood template, in reading order
# (top→bottom, left→right). Bit i corresponds to _COLORING_LABELS[i].
_COLORING_LABELS = ['NW', 'N ', 'NE',
                    'W ', 'C ', 'E ',
                    'SW', 'S ', 'SE']
# Histogram bins for per-LUT-index (dx, dy) outputs (range [-15, 15])
_COLORING_HIST_N = 31 * 31

# Time-series probe: trace names + render colors (ARGB)
_TS_TRACES = ('population', 'food_bug')
_TS_COLORS = (0xFF44DD44, 0xFFFFAA22)   # green, orange
_TS_N      = len(_TS_TRACES)


def available_probes():
    """Return a dict mapping probe names to short descriptions."""
    return dict(_AVAILABLE_PROBES)


# Module-level handle: stop any previous session before starting a new one.
_active_stop = None


def run_with_controls(sim, cell_px=None, colormode=0, paused=True, probes=None):
    """
    Display ipywidgets controls and open an SDL2 simulation window.

    Returns immediately (non-blocking).  The simulation runs in a background
    thread; the SDL2 display runs in a subprocess.

    Parameters
    ----------
    sim       : initialised Bugs instance
    cell_px   : screen pixels per cell (default: sim.cell_px from CELL_PX #define)
    colormode : initial colour mode (0=red-bugs, 1=genome-hash, 2=bug-food)
    paused    : if True, start in paused state
    probes    : dict of probe names to enable, e.g. {'activity': True, 'q_activity': True}

    Returns
    -------
    threading.Thread — the simulation thread (can be .join()-ed if desired)
    """
    global _active_stop
    if _active_stop is not None:
        _active_stop()
        _active_stop = None

    N  = sim.N
    px = cell_px if cell_px is not None else sim.cell_px

    # ── Shared memory ─────────────────────────────────────────────
    pixel_shm = SharedMemory(create=True, size=N * N * 4)
    ctrl_shm  = SharedMemory(create=True, size=5 * 4)

    pixels = np.ndarray((N * N,), dtype=np.int32, buffer=pixel_shm.buf)
    ctrl   = np.ndarray((5,),     dtype=np.int32, buffer=ctrl_shm.buf)
    ctrl[:] = [0, colormode, 0, 0, int(paused)]

    # ── G-activity probe setup (per whole-genome content hash) ──────
    G_activity_enabled = bool((probes or {}).get('G-activity'))
    ACT_H = 2 * PROBE_H  # 256 px tall
    G_activity_shm     = None
    G_activity_cursor  = None
    G_activity_pixels  = None
    G_activity_col     = None

    if G_activity_enabled:
        act_shm_size = 4 + PROBE_W * ACT_H * 4
        G_activity_shm = SharedMemory(create=True, size=act_shm_size)
        _abuf = np.ndarray((act_shm_size,), dtype=np.uint8,
                           buffer=G_activity_shm.buf)
        _abuf[:] = 0
        G_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                       buffer=G_activity_shm.buf)
        G_activity_pixels = np.ndarray((ACT_H, PROBE_W), dtype=np.int32,
                                       buffer=G_activity_shm.buf, offset=4)
        G_activity_col = np.zeros(ACT_H, dtype=np.int32)

    # ── Gq-activity (deciles of G-activity) probe setup ─────────────
    Gq_activity_enabled  = bool((probes or {}).get('Gq-activity'))
    QA_N_DECILES         = 9
    Gq_activity_shm      = None
    Gq_activity_cursor   = None
    Gq_activity_deciles  = None
    Gq_activity_col      = None

    if Gq_activity_enabled:
        qa_shm_size = 4 + QA_N_DECILES * PROBE_W * 4
        Gq_activity_shm = SharedMemory(create=True, size=qa_shm_size)
        _qabuf = np.ndarray((qa_shm_size,), dtype=np.uint8,
                             buffer=Gq_activity_shm.buf)
        _qabuf[:] = 0
        Gq_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                        buffer=Gq_activity_shm.buf)
        Gq_activity_deciles = []
        off = 4
        for _ in range(QA_N_DECILES):
            Gq_activity_deciles.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=Gq_activity_shm.buf, offset=off))
            off += PROBE_W * 4
        Gq_activity_col = np.zeros(QA_N_DECILES, dtype=np.float32)

    # ── g-activity probe setup (per (nbhd, move) LUT-slot pair) ─────
    g_activity_enabled = bool((probes or {}).get('g-activity'))
    g_activity_shm     = None
    g_activity_cursor  = None
    g_activity_pixels  = None
    g_activity_col     = None

    if g_activity_enabled:
        gact_shm_size = 4 + PROBE_W * ACT_H * 4
        g_activity_shm = SharedMemory(create=True, size=gact_shm_size)
        _gbuf = np.ndarray((gact_shm_size,), dtype=np.uint8,
                           buffer=g_activity_shm.buf)
        _gbuf[:] = 0
        g_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                       buffer=g_activity_shm.buf)
        g_activity_pixels = np.ndarray((ACT_H, PROBE_W), dtype=np.int32,
                                       buffer=g_activity_shm.buf, offset=4)
        g_activity_col = np.zeros(ACT_H, dtype=np.int32)

    # ── gq-activity (deciles of g-activity) probe setup ─────────────
    gq_activity_enabled  = bool((probes or {}).get('gq-activity'))
    gq_activity_shm      = None
    gq_activity_cursor   = None
    gq_activity_deciles  = None
    gq_activity_col      = None

    if gq_activity_enabled:
        gqa_shm_size = 4 + QA_N_DECILES * PROBE_W * 4
        gq_activity_shm = SharedMemory(create=True, size=gqa_shm_size)
        _gqabuf = np.ndarray((gqa_shm_size,), dtype=np.uint8,
                             buffer=gq_activity_shm.buf)
        _gqabuf[:] = 0
        gq_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                         buffer=gq_activity_shm.buf)
        gq_activity_deciles = []
        off = 4
        for _ in range(QA_N_DECILES):
            gq_activity_deciles.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=gq_activity_shm.buf, offset=off))
            off += PROBE_W * 4
        gq_activity_col = np.zeros(QA_N_DECILES, dtype=np.float32)

    # ── Egenome probe setup ─────────────────────────────────────────
    # shm layout: 4 B cursor + 9 mean traces (float32, PROBE_W each)
    #                        + 9 std  traces (float32, PROBE_W each)
    egenome_enabled      = bool((probes or {}).get('egenome'))
    egenome_shm          = None
    egenome_cursor       = None
    egenome_means        = None   # list of 9 np.ndarray (float32, PROBE_W)
    egenome_stds         = None

    if egenome_enabled:
        eg_shm_size = 4 + 2 * _EG_N_POS * PROBE_W * 4
        egenome_shm = SharedMemory(create=True, size=eg_shm_size)
        _egbuf = np.ndarray((eg_shm_size,), dtype=np.uint8,
                            buffer=egenome_shm.buf)
        _egbuf[:] = 0
        egenome_cursor = np.ndarray((1,), dtype=np.int32,
                                    buffer=egenome_shm.buf)
        egenome_means = []
        egenome_stds  = []
        off = 4
        for _ in range(_EG_N_POS):
            egenome_means.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=egenome_shm.buf, offset=off))
            off += PROBE_W * 4
        for _ in range(_EG_N_POS):
            egenome_stds.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=egenome_shm.buf, offset=off))
            off += PROBE_W * 4

    # ── Time-series (ts) probe setup ────────────────────────────────
    ts_enabled     = bool((probes or {}).get('ts'))
    ts_shm         = None
    ts_cursor      = None
    ts_traces      = None

    if ts_enabled:
        ts_shm_size = 4 + _TS_N * PROBE_W * 4
        ts_shm = SharedMemory(create=True, size=ts_shm_size)
        _tsbuf = np.ndarray((ts_shm_size,), dtype=np.uint8,
                            buffer=ts_shm.buf)
        _tsbuf[:] = 0
        ts_cursor = np.ndarray((1,), dtype=np.int32,
                               buffer=ts_shm.buf)
        ts_traces = []
        off = 4
        for _ in range(_TS_N):
            ts_traces.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=ts_shm.buf, offset=off))
            off += PROBE_W * 4

    # ── Bug-coloring probe setup ───────────────────────────────────
    coloring_enabled = bool((probes or {}).get('coloring'))
    coloring_shm     = None
    coloring_idx     = None   # shm[0]: int32 LUT index (0..N_GENES-1)
    coloring_hist    = None   # shm[1..962]: int32 31x31 histogram

    if coloring_enabled:
        c_shm_size = 4 + _COLORING_HIST_N * 4
        coloring_shm = SharedMemory(create=True, size=c_shm_size)
        _cbuf = np.ndarray((c_shm_size,), dtype=np.uint8,
                            buffer=coloring_shm.buf)
        _cbuf[:] = 0
        coloring_idx  = np.ndarray((1,), dtype=np.int32,
                                   buffer=coloring_shm.buf)
        coloring_hist = np.ndarray((31, 31), dtype=np.int32,
                                   buffer=coloring_shm.buf, offset=4)

    # ── SDL2 subprocess ───────────────────────────────────────────
    cmd = [sys.executable, _WORKER,
           pixel_shm.name, ctrl_shm.name, str(N), str(px)]
    if G_activity_enabled:
        cmd += ["--G-activity=" + G_activity_shm.name]
    if Gq_activity_enabled:
        cmd += ["--Gq-activity=" + Gq_activity_shm.name]
    if g_activity_enabled:
        cmd += ["--g-activity=" + g_activity_shm.name]
    if gq_activity_enabled:
        cmd += ["--gq-activity=" + gq_activity_shm.name]
    if egenome_enabled:
        cmd += ["--egenome=" + egenome_shm.name]
    if ts_enabled:
        cmd += ["--ts=" + ts_shm.name]
    if coloring_enabled:
        cmd += ["--coloring=" + coloring_shm.name]
    sdl_proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    def _reader():
        for line in sdl_proc.stdout:
            print(line.decode(errors='replace'), end='', flush=True)

    threading.Thread(target=_reader, name="bugs-sdl-reader", daemon=True).start()

    # ── Shared sim state ──────────────────────────────────────────
    st    = dict(paused=bool(paused), running=True, colormode=colormode, step_cnt=0)
    _alive        = [True]
    _cleanup_done = [False]

    def _do_cleanup():
        if _cleanup_done[0]:
            return
        _cleanup_done[0] = True
        _alive[0] = False
        if sdl_proc.poll() is None:
            sdl_proc.terminate()
            try:
                sdl_proc.wait(timeout=2)
            except Exception:
                pass
        all_shm = [pixel_shm, ctrl_shm]
        if G_activity_shm is not None:
            all_shm.append(G_activity_shm)
        if Gq_activity_shm is not None:
            all_shm.append(Gq_activity_shm)
        if g_activity_shm is not None:
            all_shm.append(g_activity_shm)
        if gq_activity_shm is not None:
            all_shm.append(gq_activity_shm)
        if egenome_shm is not None:
            all_shm.append(egenome_shm)
        if ts_shm is not None:
            all_shm.append(ts_shm)
        if coloring_shm is not None:
            all_shm.append(coloring_shm)
        for shm in all_shm:
            try:
                shm.unlink()
            except Exception:
                pass
            try:
                shm.close()
            except Exception:
                pass

    atexit.register(_do_cleanup)

    def _stop():
        global _active_stop
        st['running'] = False
        if _alive[0]:
            ctrl[_QUIT] = 1
        time.sleep(0.1)
        _do_cleanup()
        _active_stop = None

    _active_stop = _stop
    sim._stop_display = _stop

    # ── ipywidgets ─────────────────────────────────────────────────
    btn_pause = widgets.ToggleButton(
        value=bool(paused), description="Run" if paused else "Pause",
        button_style="", layout=widgets.Layout(width="90px"))
    btn_restart = widgets.Button(
        description="Restart", layout=widgets.Layout(width="80px"))
    btn_step  = widgets.Button(
        description="Step",  layout=widgets.Layout(width="70px"))
    btn_quit  = widgets.Button(
        description="Quit",  button_style="danger",
        layout=widgets.Layout(width="70px"))
    btn_save  = widgets.Button(
        description="Save Plots", layout=widgets.Layout(width="100px"))
    txt_descriptor = widgets.Text(
        placeholder='run descriptor', layout=widgets.Layout(width="200px"))
    btn_export = widgets.Button(
        description="Export", layout=widgets.Layout(width="70px"))

    sl_kw = dict(continuous_update=True,
                 style={"description_width": "120px"},
                 layout=widgets.Layout(width="440px"))
    sl_mutation_rate = widgets.FloatSlider(
        value=sim.mutation_rate, min=0.0, max=0.1, step=0.0005,
        description="mutation_rate:", readout_format=".4f", **sl_kw)
    sl_reproduction_food = widgets.FloatSlider(
        value=sim.reproduction_food, min=1.0, max=60.0, step=0.5,
        description="reproduction_food:", readout_format=".1f", **sl_kw)
    sl_movement_cost = widgets.FloatSlider(
        value=sim.movement_cost, min=0.0, max=5.0, step=0.01,
        description="movement_cost:", readout_format=".2f", **sl_kw)
    sl_eat_amount = widgets.FloatSlider(
        value=sim.eat_amount, min=0.0, max=10.0, step=0.05,
        description="eat_amount:", readout_format=".2f", **sl_kw)
    sl_initial_food = widgets.FloatSlider(
        value=sim.initial_food, min=0.0, max=30.0, step=0.5,
        description="initial_food:", readout_format=".1f", **sl_kw)
    sl_food_inc = widgets.FloatSlider(
        value=sim.food_inc, min=0.0, max=1.0, step=0.005,
        description="food_inc:", readout_format=".3f", **sl_kw)
    sl_mu_egenome = widgets.FloatSlider(
        value=sim.mu_egenome, min=0.0, max=0.1, step=0.001,
        description="mu_egenome:", readout_format=".3f", **sl_kw)
    sl_gdiff = widgets.IntSlider(
        value=sim.gdiff, min=0, max=10, step=1,
        description="gdiff:",
        style={"description_width": "120px"},
        layout=widgets.Layout(width="440px"))
    sl_move_range = widgets.IntSlider(
        value=sim.move_range, min=1, max=15, step=1,
        description="move_range:",
        style={"description_width": "120px"},
        layout=widgets.Layout(width="440px"))

    # ipywidgets silently clamps `value` to [min, max] at construction,
    # *before* any observer fires — so an init value outside a slider's
    # range leaves the C core and the slider disagreeing. Push each
    # (possibly clamped) slider value back into sim so display and core
    # stay consistent. Warn if a clamp actually happened.
    for _attr, _sl in (("mutation_rate",     sl_mutation_rate),
                       ("reproduction_food", sl_reproduction_food),
                       ("movement_cost",     sl_movement_cost),
                       ("eat_amount",        sl_eat_amount),
                       ("initial_food",      sl_initial_food),
                       ("food_inc",          sl_food_inc),
                       ("mu_egenome",        sl_mu_egenome),
                       ("gdiff",             sl_gdiff),
                       ("move_range",        sl_move_range)):
        _live = getattr(sim, _attr)
        if _sl.value != _live:
            print(f"[controls] {_attr}={_live!r} is outside the slider range "
                  f"[{_sl.min}, {_sl.max}]; clamping to {_sl.value!r}.")
            getattr(sim, f"update_{_attr}")(_sl.value)

    # ── ymax halve / double buttons ──────────────────────────────────
    def _make_ymax_btns(name, initial, update_fn):
        val = [initial]
        lbl = widgets.Label(value=f"{name}: {initial}",
                            layout=widgets.Layout(width="160px"))
        btn_h = widgets.Button(description="<|",
                               layout=widgets.Layout(width="35px"))
        btn_d = widgets.Button(description="|>",
                               layout=widgets.Layout(width="35px"))
        def halve(_):
            if not _alive[0]: return
            val[0] = max(val[0] // 2, 100)
            update_fn(val[0])
            lbl.value = f"{name}: {val[0]}"
        def double(_):
            if not _alive[0]: return
            val[0] *= 2
            update_fn(val[0])
            lbl.value = f"{name}: {val[0]}"
        btn_h.on_click(halve)
        btn_d.on_click(double)
        return widgets.HBox([btn_h, lbl, btn_d])

    _ymax_btns = []
    if G_activity_enabled:
        _ymax_btns.append(_make_ymax_btns(
            "G_act_ymax", 2000, sim.update_G_act_ymax))
    if g_activity_enabled:
        _ymax_btns.append(_make_ymax_btns(
            "g_act_ymax", 2000, sim.update_g_act_ymax))

    # ── Bug-coloring 3x3 template toggles ─────────────────────────────
    coloring_box    = None
    coloring_lbl    = None
    _coloring_btns  = []

    def _update_coloring_idx():
        if not coloring_enabled:
            return
        idx = 0
        for bi, btn in enumerate(_coloring_btns):
            if btn.value:
                idx |= (1 << bi)
        coloring_idx[0] = idx
        if coloring_lbl is not None:
            coloring_lbl.value = f"LUT idx = {idx}"

    if coloring_enabled:
        for bi, label in enumerate(_COLORING_LABELS):
            tb = widgets.ToggleButton(
                value=False, description=label.strip(),
                layout=widgets.Layout(width="40px", height="32px"))
            tb.observe(lambda _c: _update_coloring_idx(), names='value')
            _coloring_btns.append(tb)
        coloring_box = widgets.GridBox(
            children=_coloring_btns,
            layout=widgets.Layout(
                grid_template_columns="repeat(3, 44px)",
                grid_gap="2px",
                width="140px"))
        coloring_lbl = widgets.Label(value="LUT idx = 0",
                                     layout=widgets.Layout(width="120px"))

    color_dd   = widgets.Dropdown(
        options=COLOR_MODES, value=COLOR_MODES[colormode],
        description="Color:",
        layout=widgets.Layout(width="220px"))
    status_lbl = widgets.Label(value="Starting…")

    _rows = [
        widgets.HBox([btn_pause, btn_restart, btn_step, btn_quit, btn_save,
                      txt_descriptor, btn_export]),
        sl_mutation_rate, sl_reproduction_food,
        sl_movement_cost, sl_eat_amount, sl_initial_food,
        sl_food_inc, sl_mu_egenome, sl_gdiff, sl_move_range,
    ]
    if _ymax_btns:
        _rows.append(widgets.HBox(_ymax_btns))
    if coloring_box is not None:
        _rows.append(widgets.HBox([coloring_box, coloring_lbl]))
    _rows.append(widgets.HBox([color_dd, status_lbl]))
    ipy_display(widgets.VBox(_rows))

    # ── Widget callbacks ──────────────────────────────────────────
    _guard = [False]

    def _set_paused(p):
        if _guard[0] or not _alive[0]:
            return
        _guard[0] = True
        st['paused']          = p
        ctrl[_PAUSED]         = int(p)
        btn_pause.value       = p
        btn_pause.description = "Run" if p else "Pause"
        _guard[0] = False

    def on_pause_toggle(change):
        _set_paused(change['new'])

    def _record_probes():
        if G_activity_enabled:
            sim._lib.bugs_activity_update()
            cur = int(G_activity_cursor[0])
            ptr = G_activity_col.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
            sim._lib.bugs_activity_render_col(ptr, ACT_H)
            G_activity_pixels[:, cur] = G_activity_col
            G_activity_cursor[0] = (cur + 1) % PROBE_W
        if Gq_activity_enabled:
            if not G_activity_enabled:
                sim._lib.bugs_activity_update()
            cur = int(Gq_activity_cursor[0])
            ptr = Gq_activity_col.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            sim._lib.bugs_q_activity_deciles(ptr)
            for di in range(QA_N_DECILES):
                Gq_activity_deciles[di][cur] = Gq_activity_col[di]
            Gq_activity_cursor[0] = (cur + 1) % PROBE_W
        if g_activity_enabled:
            sim._lib.bugs_g_activity_update()
            cur = int(g_activity_cursor[0])
            ptr = g_activity_col.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
            sim._lib.bugs_g_activity_render_col(ptr, ACT_H)
            g_activity_pixels[:, cur] = g_activity_col
            g_activity_cursor[0] = (cur + 1) % PROBE_W
        if gq_activity_enabled:
            if not g_activity_enabled:
                sim._lib.bugs_g_activity_update()
            cur = int(gq_activity_cursor[0])
            ptr = gq_activity_col.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            sim._lib.bugs_gq_activity_deciles(ptr)
            for di in range(QA_N_DECILES):
                gq_activity_deciles[di][cur] = gq_activity_col[di]
            gq_activity_cursor[0] = (cur + 1) % PROBE_W
        if egenome_enabled:
            mean, std = sim.egenome_stats()
            cur = int(egenome_cursor[0])
            for pi in range(_EG_N_POS):
                egenome_means[pi][cur] = mean[pi]
                egenome_stds [pi][cur] = std [pi]
            egenome_cursor[0] = (cur + 1) % PROBE_W
        if ts_enabled:
            ts_cur = int(ts_cursor[0])
            ts_traces[0][ts_cur] = float(sim.get_population())
            ts_traces[1][ts_cur] = float(sim.get_food_bug())
            ts_cursor[0] = (ts_cur + 1) % PROBE_W
        if coloring_enabled:
            gi = int(coloring_idx[0])
            hist_ptr = coloring_hist.ctypes.data_as(
                ctypes.POINTER(ctypes.c_int32))
            sim._lib.bugs_bug_coloring_hist(gi, hist_ptr)

    def on_step(_):
        if not _alive[0]:
            return
        if st['paused']:
            sim.step()
            st['step_cnt'] += 1
            ctrl[_STEP] = st['step_cnt']
            sim.colorize(pixels, st['colormode'])
            _record_probes()
            status_lbl.value = (
                f"t={st['step_cnt']}  pop={sim.get_population()}  (paused)")

    def on_quit(_):
        st['running'] = False
        if _alive[0]:
            ctrl[_QUIT] = 1
        status_lbl.value = "Stopped — call sim.free() when ready"

    def on_color(change):
        if not _alive[0]:
            return
        cm = COLOR_MODES.index(change['new'])
        st['colormode'] = cm
        ctrl[_CMODE]    = cm

    def on_save(_):
        if not _alive[0]:
            return
        saved = 0

        def _save_deciles(name, cursor, deciles):
            cur = int(cursor[0])
            t   = np.arange(PROBE_W)
            fig, ax = plt.subplots(figsize=(8, 3))
            for di in range(QA_N_DECILES):
                y = np.roll(deciles[di], -cur)
                ax.plot(t, y, linewidth=0.6, label=f"p{(di+1)*10}")
            ax.set_yscale('log')
            ax.set_title(f"{name} deciles")
            ax.set_xlabel("t (relative)")
            ax.legend(ncol=3, fontsize=7)
            fig.tight_layout()
            fig.savefig(f"probe_{name}.png", dpi=150)
            plt.close(fig)

        if Gq_activity_enabled:
            _save_deciles("Gq_activity", Gq_activity_cursor, Gq_activity_deciles)
            saved += 1
        if gq_activity_enabled:
            _save_deciles("gq_activity", gq_activity_cursor, gq_activity_deciles)
            saved += 1
        if egenome_enabled:
            cur = int(egenome_cursor[0])
            t   = np.arange(PROBE_W)
            pos_labels = ['NW', 'N', 'NE', 'W', 'C', 'E', 'SW', 'S', 'SE']
            fig, ax = plt.subplots(figsize=(8, 3))
            for pi in range(_EG_N_POS):
                m = np.roll(egenome_means[pi], -cur)
                s = np.roll(egenome_stds [pi], -cur)
                line, = ax.plot(t, m, linewidth=0.9, label=pos_labels[pi])
                ax.fill_between(t, m - s, m + s, color=line.get_color(),
                                alpha=0.15, linewidth=0)
            ax.set_ylim(0.0, 1.0)
            ax.set_title("egenome per-position mean ± std")
            ax.set_xlabel("t (relative)")
            ax.legend(ncol=3, fontsize=7)
            fig.tight_layout()
            fig.savefig("probe_egenome.png", dpi=150)
            plt.close(fig)
            saved += 1
        if ts_enabled:
            cur = int(ts_cursor[0])
            t   = np.arange(PROBE_W)
            fig, ax = plt.subplots(figsize=(8, 3))
            for ti, name in enumerate(_TS_TRACES):
                y = np.roll(ts_traces[ti], -cur)
                ax.plot(t, y, linewidth=0.8, label=name)
            ax.set_yscale('log')
            ax.set_title("time series")
            ax.set_xlabel("t (relative)")
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig("probe_ts.png", dpi=150)
            plt.close(fig)
            saved += 1
        status_lbl.value = f"Saved {saved} probe plot(s)" if saved \
                           else "No scalar probes to save"

    def on_export(_):
        desc = txt_descriptor.value.strip() or 'unnamed'
        cm = COLOR_MODES.index(color_dd.value) if color_dd.value in COLOR_MODES else 0
        path = sim.export_recipe(desc, probes=probes, colormode=cm)
        status_lbl.value = f"Exported: {path}"

    def on_restart(_):
        if not _alive[0]:
            return
        _set_paused(True)
        time.sleep(0.02)

        saved_state = dict(sim._state_params)

        sim._lib.bugs_init(N)
        for k in sim._DEFAULTS:
            getattr(sim._lib, f"bugs_set_{k}")(getattr(sim, k))

        sim.state(**saved_state)

        st['step_cnt'] = 0
        ctrl[_STEP] = 0

        if G_activity_enabled:
            G_activity_cursor[0] = 0
            G_activity_pixels[:] = 0
        if Gq_activity_enabled:
            Gq_activity_cursor[0] = 0
            for di in range(QA_N_DECILES):
                Gq_activity_deciles[di][:] = 0
        if g_activity_enabled:
            g_activity_cursor[0] = 0
            g_activity_pixels[:] = 0
        if gq_activity_enabled:
            gq_activity_cursor[0] = 0
            for di in range(QA_N_DECILES):
                gq_activity_deciles[di][:] = 0
        if egenome_enabled:
            egenome_cursor[0] = 0
            for pi in range(_EG_N_POS):
                egenome_means[pi][:] = 0
                egenome_stds [pi][:] = 0
        if ts_enabled:
            ts_cursor[0] = 0
            for ti in range(_TS_N):
                ts_traces[ti][:] = 0

        sim.colorize(pixels, st['colormode'])
        status_lbl.value = "Restarted — t=0  (paused)"

    btn_pause.observe(on_pause_toggle, names='value')
    btn_restart.on_click(on_restart)
    btn_step.on_click(on_step)
    btn_quit.on_click(on_quit)
    btn_save.on_click(on_save)
    btn_export.on_click(on_export)
    color_dd.observe(on_color, names='value')

    def _make_slider_cb(attr, slider):
        _timer      = [None]
        _was_paused = [False]

        def on_value(change):
            if not _alive[0]:
                return
            if not st['paused']:
                _was_paused[0] = False
                _set_paused(True)
            else:
                _was_paused[0] = True
            getattr(sim, f"update_{attr}")(change['new'])
            if _timer[0] is not None:
                _timer[0].cancel()

            def _resume():
                if not _alive[0]:
                    return
                if not _was_paused[0]:
                    st['paused']  = False
                    ctrl[_PAUSED] = 0

            _timer[0] = threading.Timer(_SLIDER_RESUME_S, _resume)
            _timer[0].start()

        slider.observe(on_value, names='value')

    _make_slider_cb("mutation_rate",     sl_mutation_rate)
    _make_slider_cb("reproduction_food", sl_reproduction_food)
    _make_slider_cb("movement_cost",     sl_movement_cost)
    _make_slider_cb("eat_amount",        sl_eat_amount)
    _make_slider_cb("initial_food",      sl_initial_food)
    _make_slider_cb("food_inc",          sl_food_inc)
    _make_slider_cb("mu_egenome",        sl_mu_egenome)
    _make_slider_cb("gdiff",             sl_gdiff)
    _make_slider_cb("move_range",        sl_move_range)

    # ── Simulation thread ─────────────────────────────────────────
    def _sim_thread():
        FPS_ALPHA = 0.05
        fps       = 0.0
        t_last    = time.perf_counter()

        while st['running'] and ctrl[_QUIT] == 0:

            if st['step_cnt'] == 5:
                rc = sdl_proc.poll()
                if rc is not None:
                    print(f"Bugs: SDL worker exited early (rc={rc})", flush=True)
                    status_lbl.value = f"SDL worker crashed (rc={rc}) — check terminal"

            if st['paused']:
                sim.colorize(pixels, st['colormode'])
                t_last = time.perf_counter()
                time.sleep(0.01)
                continue

            sim.step()
            st['step_cnt'] += 1

            sim.colorize(pixels, st['colormode'])

            _record_probes()

            t_now = time.perf_counter()
            dt    = t_now - t_last
            t_last = t_now
            if dt > 0:
                fps = FPS_ALPHA * (1.0 / dt) + (1.0 - FPS_ALPHA) * fps

            sc           = st['step_cnt']
            ctrl[_STEP]  = sc
            ctrl[_FPS10] = int(fps * 10)

            if sc % 100 == 0:
                pop = sim.get_population()
                status_lbl.value = f"t={sc}  pop={pop}  fps={fps:.1f}"

        st['running'] = False
        if _alive[0]:
            ctrl[_QUIT] = 1
        try:
            sdl_proc.wait(timeout=3)
        except Exception:
            pass
        _do_cleanup()

    t = threading.Thread(target=_sim_thread, name="bugs-sim", daemon=True)
    t.start()
    return t
