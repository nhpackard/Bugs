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
PROBE_W = 512
PROBE_H = 128

_AVAILABLE_PROBES = {
    'activity':   'Per-genome activity (scrolling hash-colored strip)',
    'q_activity': 'Activity quantile profile (decile strip chart)',
}


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

    # ── Activity probe setup ────────────────────────────────────────
    activity_enabled = bool((probes or {}).get('activity'))
    ACT_H = 2 * PROBE_H  # 256 px tall
    activity_shm     = None
    activity_cursor  = None
    activity_pixels  = None
    activity_col     = None

    if activity_enabled:
        act_shm_size = 4 + PROBE_W * ACT_H * 4
        activity_shm = SharedMemory(create=True, size=act_shm_size)
        _abuf = np.ndarray((act_shm_size,), dtype=np.uint8,
                           buffer=activity_shm.buf)
        _abuf[:] = 0
        activity_cursor = np.ndarray((1,), dtype=np.int32,
                                     buffer=activity_shm.buf)
        activity_pixels = np.ndarray((ACT_H, PROBE_W), dtype=np.int32,
                                     buffer=activity_shm.buf, offset=4)
        activity_col = np.zeros(ACT_H, dtype=np.int32)

    # ── Activity quantile (q_activity) probe setup ──────────────────
    q_activity_enabled  = bool((probes or {}).get('q_activity'))
    QA_N_DECILES        = 9
    q_activity_shm      = None
    q_activity_cursor   = None
    q_activity_deciles  = None
    q_activity_col      = None

    if q_activity_enabled:
        qa_shm_size = 4 + QA_N_DECILES * PROBE_W * 4
        q_activity_shm = SharedMemory(create=True, size=qa_shm_size)
        _qabuf = np.ndarray((qa_shm_size,), dtype=np.uint8,
                             buffer=q_activity_shm.buf)
        _qabuf[:] = 0
        q_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                        buffer=q_activity_shm.buf)
        q_activity_deciles = []
        off = 4
        for _ in range(QA_N_DECILES):
            q_activity_deciles.append(
                np.ndarray((PROBE_W,), dtype=np.float32,
                           buffer=q_activity_shm.buf, offset=off))
            off += PROBE_W * 4
        q_activity_col = np.zeros(QA_N_DECILES, dtype=np.float32)

    # ── SDL2 subprocess ───────────────────────────────────────────
    cmd = [sys.executable, _WORKER,
           pixel_shm.name, ctrl_shm.name, str(N), str(px)]
    if activity_enabled:
        cmd += ["--activity=" + activity_shm.name]
    if q_activity_enabled:
        cmd += ["--q-activity=" + q_activity_shm.name]
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
        if activity_shm is not None:
            all_shm.append(activity_shm)
        if q_activity_shm is not None:
            all_shm.append(q_activity_shm)
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
        value=sim.food_inc, min=0.0, max=0.2, step=0.001,
        description="food_inc:", readout_format=".3f", **sl_kw)
    sl_food_threshold = widgets.FloatSlider(
        value=sim.food_threshold, min=0.0, max=1.0, step=0.01,
        description="food_threshold:", readout_format=".2f", **sl_kw)
    sl_gdiff = widgets.IntSlider(
        value=sim.gdiff, min=0, max=10, step=1,
        description="gdiff:",
        style={"description_width": "120px"},
        layout=widgets.Layout(width="440px"))

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
    if activity_enabled:
        _ymax_btns.append(_make_ymax_btns(
            "act_ymax", 2000, sim.update_act_ymax))

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
        sl_food_inc, sl_food_threshold, sl_gdiff,
    ]
    if _ymax_btns:
        _rows.append(widgets.HBox(_ymax_btns))
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
        if activity_enabled:
            sim._lib.bugs_activity_update()
            act_cur = int(activity_cursor[0])
            act_col_ptr = activity_col.ctypes.data_as(
                ctypes.POINTER(ctypes.c_int32))
            sim._lib.bugs_activity_render_col(act_col_ptr, ACT_H)
            activity_pixels[:, act_cur] = activity_col
            activity_cursor[0] = (act_cur + 1) % PROBE_W
        if q_activity_enabled:
            if not activity_enabled:
                sim._lib.bugs_activity_update()
            qa_cur = int(q_activity_cursor[0])
            qa_col_ptr = q_activity_col.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float))
            sim._lib.bugs_q_activity_deciles(qa_col_ptr)
            for di in range(QA_N_DECILES):
                q_activity_deciles[di][qa_cur] = q_activity_col[di]
            q_activity_cursor[0] = (qa_cur + 1) % PROBE_W

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
        if q_activity_enabled:
            cur = int(q_activity_cursor[0])
            t   = np.arange(PROBE_W)
            fig, ax = plt.subplots(figsize=(8, 3))
            for di in range(QA_N_DECILES):
                y = np.roll(q_activity_deciles[di], -cur)
                ax.plot(t, y, linewidth=0.6, label=f"p{(di+1)*10}")
            ax.set_yscale('log')
            ax.set_title("q_activity deciles")
            ax.set_xlabel("t (relative)")
            ax.legend(ncol=3, fontsize=7)
            fig.tight_layout()
            fig.savefig("probe_q_activity.png", dpi=150)
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

        if activity_enabled:
            activity_cursor[0] = 0
            activity_pixels[:] = 0
        if q_activity_enabled:
            q_activity_cursor[0] = 0
            for di in range(QA_N_DECILES):
                q_activity_deciles[di][:] = 0

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
    _make_slider_cb("food_threshold",    sl_food_threshold)
    _make_slider_cb("gdiff",             sl_gdiff)

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
