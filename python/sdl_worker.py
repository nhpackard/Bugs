"""
sdl_worker.py — SDL2 display subprocess for Bugs.

Launched by controls.run_with_controls() via subprocess.Popen.
All output goes to the terminal where Jupyter was started.

Usage (internal):
    python sdl_worker.py <pixel_shm> <ctrl_shm> <N> <px> \\
                         [--G-activity=<shm>]  [--Gq-activity=<shm>] \\
                         [--g-activity=<shm>]  [--gq-activity=<shm>] \\
                         [--ts=<shm>] [--coloring=<shm>]

ctrl_shm layout (5 × int32)
    [0] quit      1 = exit
    [1] colormode 0/1/2
    [2] step_cnt
    [3] fps × 10
    [4] paused    0/1
"""
import ctypes
import math
import sys
import traceback

PROBE_W     = 1024
PROBE_H     = 128
TITLE_BAR_H = 28   # macOS title bar estimate

# Bug-coloring histogram window: 31x31 bins × BIN_PX = window size.
COLORING_BIN_PX = 10
COLORING_W      = 31 * COLORING_BIN_PX   # 310
COLORING_H      = 31 * COLORING_BIN_PX


def _c(argb):
    """Convert ARGB uint32 to np.int32 (avoids numpy deprecation warning)."""
    import numpy as np
    return np.int32(argb if argb < 0x80000000 else argb - 0x100000000)


BG_COLOR     = _c(0xFF1A1A1A)
CURSOR_COLOR = _c(0xFF444444)

# Decile colors for q_activity (p10 blue → p50 green → p90 red)
_QA_COLORS = [
    _c(0xFF3344FF),  # p10 - blue
    _c(0xFF2288FF),  # p20
    _c(0xFF00BBDD),  # p30 - cyan
    _c(0xFF00CC88),  # p40 - teal
    _c(0xFF44DD44),  # p50 - green (median)
    _c(0xFFBBBB00),  # p60 - yellow
    _c(0xFFFF8800),  # p70 - orange
    _c(0xFFFF4422),  # p80
    _c(0xFFFF1144),  # p90 - red
]

# Time-series trace colors (must match _TS_COLORS in controls.py).
_TS_COLORS = [
    _c(0xFF44DD44),  # population - green
    _c(0xFFFFAA22),  # food_bug   - orange
]
_TS_LABELS = ['pop', 'food_bug']

# Egenome 9-position palette, order [NW, N, NE, W, C, E, SW, S, SE].
# Packed (R, G, B) with alpha applied at blend time.
_EG_RGB = (
    (0xFF, 0x44, 0x44),  # NW red
    (0xFF, 0x99, 0x44),  # N  orange
    (0xFF, 0xDD, 0x44),  # NE yellow
    (0xAA, 0xFF, 0x44),  # W  lime
    (0x44, 0xFF, 0x88),  # C  green
    (0x44, 0xDD, 0xFF),  # E  cyan
    (0x44, 0x88, 0xFF),  # SW blue
    (0xAA, 0x44, 0xFF),  # S  violet
    (0xFF, 0x44, 0xDD),  # SE magenta
)
_EG_N_POS = 9
_EG_LABELS = ('NW', 'N', 'NE', 'W', 'C', 'E', 'SW', 'S', 'SE')


def _render_q_activity(dst, decile_bufs, cursor, global_max):
    """Render activity quantile strip chart with log-scaled Y axis.

    decile_bufs: list of 9 float32[PROBE_W] arrays (p10..p90).
    global_max:  all-time observed max (float); updated and returned.
    """
    import numpy as np

    dst[:PROBE_H, :PROBE_W] = BG_COLOR

    rolled = [np.roll(b, -cursor) for b in decile_bufs]

    all_pos = []
    for r in rolled:
        pos = r[r > 0]
        if len(pos) > 0:
            all_pos.append(pos)
    if len(all_pos) == 0:
        return global_max
    cat = np.concatenate(all_pos)
    lo = float(cat.min())
    hi = float(cat.max())

    global_max = max(global_max, hi)

    if lo <= 0:
        lo = float(cat[cat > 0].min()) if (cat > 0).any() else 1.0
    hi = global_max
    if hi <= lo:
        hi = lo * 10.0
    log_lo = math.log10(lo)
    log_hi = math.log10(hi)
    span = log_hi - log_lo
    if span < 0.01:
        span = 1.0
    log_hi += span * 0.10
    scale = (PROBE_H - 1) / (log_hi - log_lo)

    xs = np.arange(PROBE_W)
    for di in range(9):
        col = _QA_COLORS[di]
        r = rolled[di]
        mask = r > 0
        if not mask.any():
            continue
        lv = np.log10(r[mask])
        ys = np.clip(((log_hi - lv) * scale).astype(int), 0, PROBE_H - 1)
        dst[ys, xs[mask]] = col

    dst[:PROBE_H, PROBE_W - 1] = CURSOR_COLOR
    return global_max


def _render_coloring(dst, hist, lut_idx):
    """Render a 31x31 (dx, dy) move histogram as filled squares with
    log-scaled intensity (grayscale).  Also draw a small 3x3 template
    representation in the top-left corner so the user can verify which
    LUT index is being probed."""
    import numpy as np

    dst[:COLORING_H, :COLORING_W] = BG_COLOR

    hmax = int(hist.max()) if hist.size else 0
    if hmax > 0:
        # log1p -> normalize so hmax maps to 255
        lg   = np.log1p(hist.astype(np.float64))
        lg  /= max(lg.max(), 1e-9)
        vals = (lg * 255.0).astype(np.int32)
        for i in range(31):       # i = dy index; visual y = COLORING_H-1 - i*BIN_PX
            for j in range(31):
                v = int(vals[i, j])
                if v <= 0:
                    continue
                # ARGB gray
                col = _c(0xFF000000 | (v << 16) | (v << 8) | v)
                y0 = (30 - i) * COLORING_BIN_PX
                x0 = j * COLORING_BIN_PX
                dst[y0:y0 + COLORING_BIN_PX,
                    x0:x0 + COLORING_BIN_PX] = col

    # Center crosshair at (dx=0, dy=0) → bin (15, 15)
    cx = 15 * COLORING_BIN_PX + COLORING_BIN_PX // 2
    cy = (30 - 15) * COLORING_BIN_PX + COLORING_BIN_PX // 2
    dst[cy, max(cx - 3, 0):min(cx + 4, COLORING_W)] = _c(0xFF4080FF)
    dst[max(cy - 3, 0):min(cy + 4, COLORING_H), cx] = _c(0xFF4080FF)

    # 3x3 template in top-left showing bits of lut_idx
    # Bit layout: [NW, N, NE, W, C, E, SW, S, SE] in reading order (row-major).
    pad = 4
    cell = 10
    for b in range(9):
        col_ = b % 3
        row  = b // 3
        x0 = pad + col_ * cell
        y0 = pad + row  * cell
        col = _c(0xFFFFFF00) if (lut_idx & (1 << b)) else _c(0xFF333333)
        dst[y0:y0 + cell - 2, x0:x0 + cell - 2] = col


def _render_ts(dst, trace_bufs, cursor, global_max):
    """Render scalar time-series as log-Y colored lines.

    trace_bufs: list of float32[PROBE_W] arrays.
    global_max: running max across the session (scales Y stably).
    """
    import numpy as np

    dst[:PROBE_H, :PROBE_W] = BG_COLOR

    rolled = [np.roll(b, -cursor) for b in trace_bufs]

    # Pool all positive samples to fix log-Y range.
    pos_samples = []
    for r in rolled:
        p = r[r > 0]
        if len(p):
            pos_samples.append(p)
    if not pos_samples:
        return global_max
    cat = np.concatenate(pos_samples)
    lo = float(cat.min())
    hi = float(cat.max())
    global_max = max(global_max, hi)
    if lo <= 0:
        lo = 1.0
    hi = global_max
    if hi <= lo:
        hi = lo * 10.0
    log_lo = math.log10(lo)
    log_hi = math.log10(hi)
    span = log_hi - log_lo
    if span < 0.01:
        span = 1.0
    log_hi += span * 0.10
    scale = (PROBE_H - 1) / (log_hi - log_lo)

    xs = np.arange(PROBE_W)
    for ti, r in enumerate(rolled):
        col = _TS_COLORS[ti % len(_TS_COLORS)]
        mask = r > 0
        if not mask.any():
            continue
        lv = np.log10(r[mask])
        ys = np.clip(((log_hi - lv) * scale).astype(int), 0, PROBE_H - 1)
        dst[ys, xs[mask]] = col

    dst[:PROBE_H, PROBE_W - 1] = CURSOR_COLOR
    return global_max


def _draw_egenome_template(dst):
    """Draw a 3x3 Moore-neighborhood legend in the upper-left corner of the
    egenome probe, styled like the coloring probe template: cells colored
    to match the 9 position traces in reading order
    [NW N NE / W C E / SW S SE]."""
    import numpy as np

    def _pack(r, g, b):
        v = (0xFF000000 | (r << 16) | (g << 8) | b) & 0xFFFFFFFF
        return np.int32(v - 0x100000000) if v >= 0x80000000 else np.int32(v)

    pad  = 4
    cell = 10
    for p in range(9):
        col_ = p % 3
        row  = p // 3
        x0 = pad + col_ * cell
        y0 = pad + row  * cell
        cr, cg, cb = _EG_RGB[p]
        dst[y0:y0 + cell - 2, x0:x0 + cell - 2] = _pack(cr, cg, cb)


def _render_egenome(dst, means, stds, cursor):
    """Render the egenome probe: 9 translucent position bands over linear
    Y axis in [0, 1]. For each position p, a filled band extends from
    mean[p]-std[p] to mean[p]+std[p], with a solid centerline at mean[p].
    Bands are blended additively so overlaps lighten.

    means, stds : list of 9 float32[PROBE_W] arrays.
    """
    import numpy as np

    # Background
    dst[:PROBE_H, :PROBE_W] = BG_COLOR

    # Unpack BG once so we can blend against it cleanly.
    bg = int(BG_COLOR) & 0xFFFFFFFF
    br = (bg >> 16) & 0xFF
    bg_g = (bg >> 8) & 0xFF
    bb = bg & 0xFF

    # Float workspace so we can blend, then convert back to int32 ARGB.
    work_r = np.full((PROBE_H, PROBE_W), br, dtype=np.float32)
    work_g = np.full((PROBE_H, PROBE_W), bg_g, dtype=np.float32)
    work_b = np.full((PROBE_H, PROBE_W), bb, dtype=np.float32)

    xs = np.arange(PROBE_W, dtype=np.int32)
    band_alpha = 0.30   # translucent band
    line_alpha = 1.00   # opaque centerline

    for p in range(_EG_N_POS):
        m = np.roll(means[p], -cursor)
        s = np.roll(stds [p], -cursor)

        # Ignore columns with no data yet (mean==0 and std==0 on init-reset).
        valid = (m > 0) | (s > 0)
        if not valid.any():
            continue

        cr, cg, cb = _EG_RGB[p]

        # Clip to [0, 1] before mapping to pixel rows.
        m_c = np.clip(m, 0.0, 1.0)
        s_c = np.clip(s, 0.0, 1.0)
        top = np.clip(m_c + s_c, 0.0, 1.0)
        bot = np.clip(m_c - s_c, 0.0, 1.0)

        # Convert to row coordinates: y=0 is top (value=1), y=H-1 is bottom (value=0).
        y_top = ((1.0 - top) * (PROBE_H - 1)).astype(np.int32)
        y_bot = ((1.0 - bot) * (PROBE_H - 1)).astype(np.int32)
        y_mid = ((1.0 - m_c) * (PROBE_H - 1)).astype(np.int32)

        # Band fill: for each valid column, blend α into rows [y_top, y_bot].
        cols = np.where(valid)[0]
        for x in cols:
            y0 = int(y_top[x])
            y1 = int(y_bot[x])
            if y0 > y1:
                y0, y1 = y1, y0
            work_r[y0:y1 + 1, x] = work_r[y0:y1 + 1, x] * (1 - band_alpha) + cr * band_alpha
            work_g[y0:y1 + 1, x] = work_g[y0:y1 + 1, x] * (1 - band_alpha) + cg * band_alpha
            work_b[y0:y1 + 1, x] = work_b[y0:y1 + 1, x] * (1 - band_alpha) + cb * band_alpha

        # Centerline.
        ys = np.clip(y_mid[valid], 0, PROBE_H - 1)
        work_r[ys, xs[valid]] = work_r[ys, xs[valid]] * (1 - line_alpha) + cr * line_alpha
        work_g[ys, xs[valid]] = work_g[ys, xs[valid]] * (1 - line_alpha) + cg * line_alpha
        work_b[ys, xs[valid]] = work_b[ys, xs[valid]] * (1 - line_alpha) + cb * line_alpha

    # Gridlines at y = 0.25, 0.50, 0.75 for readability
    for v in (0.25, 0.5, 0.75):
        y = int((1.0 - v) * (PROBE_H - 1))
        work_r[y, :] = np.clip(work_r[y, :] + 20, 0, 255)
        work_g[y, :] = np.clip(work_g[y, :] + 20, 0, 255)
        work_b[y, :] = np.clip(work_b[y, :] + 20, 0, 255)

    # Pack to ARGB int32
    r = np.clip(work_r, 0, 255).astype(np.uint32)
    g = np.clip(work_g, 0, 255).astype(np.uint32)
    b = np.clip(work_b, 0, 255).astype(np.uint32)
    argb = (0xFF000000 | (r << 16) | (g << 8) | b).astype(np.int64)
    argb = np.where(argb < 0x80000000, argb, argb - 0x100000000).astype(np.int32)
    dst[:PROBE_H, :PROBE_W] = argb

    # 3x3 Moore-neighborhood legend in upper-left.
    _draw_egenome_template(dst)

    # Cursor marker
    dst[:PROBE_H, PROBE_W - 1] = CURSOR_COLOR


def main():
    if len(sys.argv) < 5:
        print("Bugs SDL: bad args", flush=True)
        sys.exit(1)

    pixel_shm_name = sys.argv[1]
    ctrl_shm_name  = sys.argv[2]
    N  = int(sys.argv[3])
    px = int(sys.argv[4])
    W, H = N * px, N * px

    G_activity_shm_name  = None
    Gq_activity_shm_name = None
    g_activity_shm_name  = None
    gq_activity_shm_name = None
    egenome_shm_name     = None
    ts_shm_name          = None
    coloring_shm_name    = None
    for arg in sys.argv[5:]:
        if arg.startswith("--G-activity="):
            G_activity_shm_name = arg[len("--G-activity="):]
        elif arg.startswith("--Gq-activity="):
            Gq_activity_shm_name = arg[len("--Gq-activity="):]
        elif arg.startswith("--g-activity="):
            g_activity_shm_name = arg[len("--g-activity="):]
        elif arg.startswith("--gq-activity="):
            gq_activity_shm_name = arg[len("--gq-activity="):]
        elif arg.startswith("--egenome="):
            egenome_shm_name = arg[len("--egenome="):]
        elif arg.startswith("--ts="):
            ts_shm_name = arg[len("--ts="):]
        elif arg.startswith("--coloring="):
            coloring_shm_name = arg[len("--coloring="):]

    ACT_H = 4 * PROBE_H  # 512

    print(f"Bugs SDL: starting  N={N} px={px}  "
          f"G-activity={bool(G_activity_shm_name)}  "
          f"Gq-activity={bool(Gq_activity_shm_name)}  "
          f"g-activity={bool(g_activity_shm_name)}  "
          f"gq-activity={bool(gq_activity_shm_name)}  "
          f"egenome={bool(egenome_shm_name)}  "
          f"ts={bool(ts_shm_name)}  "
          f"coloring={bool(coloring_shm_name)}", flush=True)

    import numpy as np
    from multiprocessing.shared_memory import SharedMemory
    import sdl2

    try:
        pixel_shm = SharedMemory(name=pixel_shm_name)
        ctrl_shm  = SharedMemory(name=ctrl_shm_name)
    except Exception as e:
        print(f"Bugs SDL: SharedMemory open failed: {e}", flush=True)
        sys.exit(1)

    pixels = np.ndarray((N * N,), dtype=np.int32, buffer=pixel_shm.buf)
    ctrl   = np.ndarray((5,),     dtype=np.int32, buffer=ctrl_shm.buf)

    # ── Helper to open an activity-strip shm ─────────────────────
    def _open_activity_shm(name, label):
        try:
            shm = SharedMemory(name=name)
            cursor = np.ndarray((1,), dtype=np.int32, buffer=shm.buf)
            pixels = np.ndarray((ACT_H, PROBE_W), dtype=np.int32,
                                buffer=shm.buf, offset=4)
            print(f"Bugs SDL: {label} shm opened ({ACT_H}x{PROBE_W})",
                  flush=True)
            return shm, cursor, pixels
        except Exception as e:
            print(f"Bugs SDL: {label} SharedMemory open failed: {e}",
                  flush=True)
            return None, None, None

    def _open_deciles_shm(name, label, n_deciles):
        try:
            shm = SharedMemory(name=name)
            cursor = np.ndarray((1,), dtype=np.int32, buffer=shm.buf)
            deciles = []
            off = 4
            for _ in range(n_deciles):
                deciles.append(
                    np.ndarray((PROBE_W,), dtype=np.float32,
                               buffer=shm.buf, offset=off))
                off += PROBE_W * 4
            print(f"Bugs SDL: {label} shm opened ({n_deciles}x{PROBE_W})",
                  flush=True)
            return shm, cursor, deciles
        except Exception as e:
            print(f"Bugs SDL: {label} SharedMemory open failed: {e}",
                  flush=True)
            return None, None, None

    # ── G-activity shared memory ─────────────────────────────────
    G_activity_shm    = None
    G_activity_cursor = None
    G_activity_pixels = None
    if G_activity_shm_name:
        G_activity_shm, G_activity_cursor, G_activity_pixels = \
            _open_activity_shm(G_activity_shm_name, "G-activity")
        if G_activity_shm is None: G_activity_shm_name = None

    # ── g-activity shared memory ─────────────────────────────────
    g_activity_shm    = None
    g_activity_cursor = None
    g_activity_pixels = None
    if g_activity_shm_name:
        g_activity_shm, g_activity_cursor, g_activity_pixels = \
            _open_activity_shm(g_activity_shm_name, "g-activity")
        if g_activity_shm is None: g_activity_shm_name = None

    # ── Gq/gq-activity shared memory ─────────────────────────────
    QA_N_DECILES         = 9
    Gq_activity_shm      = None
    Gq_activity_cursor   = None
    Gq_activity_deciles  = None
    if Gq_activity_shm_name:
        Gq_activity_shm, Gq_activity_cursor, Gq_activity_deciles = \
            _open_deciles_shm(Gq_activity_shm_name, "Gq-activity", QA_N_DECILES)
        if Gq_activity_shm is None: Gq_activity_shm_name = None

    gq_activity_shm      = None
    gq_activity_cursor   = None
    gq_activity_deciles  = None
    if gq_activity_shm_name:
        gq_activity_shm, gq_activity_cursor, gq_activity_deciles = \
            _open_deciles_shm(gq_activity_shm_name, "gq-activity", QA_N_DECILES)
        if gq_activity_shm is None: gq_activity_shm_name = None

    # ── Egenome shared memory (9 means + 9 stds) ─────────────────
    egenome_shm     = None
    egenome_cursor  = None
    egenome_means   = None
    egenome_stds    = None
    if egenome_shm_name:
        try:
            egenome_shm = SharedMemory(name=egenome_shm_name)
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
            print(f"Bugs SDL: egenome shm opened ({_EG_N_POS}x{PROBE_W} means+stds)",
                  flush=True)
        except Exception as e:
            print(f"Bugs SDL: egenome SharedMemory open failed: {e}",
                  flush=True)
            egenome_shm_name = None
            egenome_shm = None

    # ── coloring shared memory ───────────────────────────────────
    coloring_shm    = None
    coloring_idx    = None   # [0]: current LUT index (0..511)
    coloring_hist   = None   # [1..961]: 31x31 int32 histogram
    if coloring_shm_name:
        try:
            coloring_shm  = SharedMemory(name=coloring_shm_name)
            coloring_idx  = np.ndarray((1,), dtype=np.int32,
                                       buffer=coloring_shm.buf)
            coloring_hist = np.ndarray((31, 31), dtype=np.int32,
                                       buffer=coloring_shm.buf, offset=4)
            print("Bugs SDL: coloring shm opened (31x31)", flush=True)
        except Exception as e:
            print(f"Bugs SDL: coloring SharedMemory open failed: {e}",
                  flush=True)
            coloring_shm_name = None

    # ── ts (time-series) shared memory ───────────────────────────
    TS_N          = len(_TS_LABELS)
    ts_shm        = None
    ts_cursor     = None
    ts_traces     = None
    if ts_shm_name:
        try:
            ts_shm = SharedMemory(name=ts_shm_name)
            ts_cursor = np.ndarray((1,), dtype=np.int32,
                                   buffer=ts_shm.buf)
            ts_traces = []
            off = 4
            for _ in range(TS_N):
                ts_traces.append(
                    np.ndarray((PROBE_W,), dtype=np.float32,
                               buffer=ts_shm.buf, offset=off))
                off += PROBE_W * 4
            print(f"Bugs SDL: ts shm opened ({TS_N}x{PROBE_W})", flush=True)
        except Exception as e:
            print(f"Bugs SDL: ts SharedMemory open failed: {e}", flush=True)
            ts_shm_name = None

    COLOR_MODES = ["red-bugs", "genome-hash", "bug-food"]

    # ── SDL2 init ─────────────────────────────────────────────────
    if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
        print(f"Bugs SDL: SDL_Init failed: {sdl2.SDL_GetError()}", flush=True)
        ctrl[0] = 1
        sys.exit(1)

    print("Bugs SDL: SDL_Init OK", flush=True)

    dm = sdl2.SDL_DisplayMode()
    sdl2.SDL_GetCurrentDisplayMode(0, ctypes.byref(dm))
    scr_w, scr_h = dm.w, dm.h

    main_x = scr_w - W
    main_y = 0

    window_p = sdl2.SDL_CreateWindow(
        b"Bugs",
        main_x, main_y,
        W, H,
        sdl2.SDL_WINDOW_SHOWN,
    )
    if not window_p:
        print(f"Bugs SDL: SDL_CreateWindow failed: {sdl2.SDL_GetError()}",
              flush=True)
        ctrl[0] = 1
        sdl2.SDL_Quit()
        sys.exit(1)

    sdl2.SDL_RaiseWindow(window_p)
    main_window_id = sdl2.SDL_GetWindowID(window_p)
    print("Bugs SDL: window created and raised", flush=True)

    surface_p = sdl2.SDL_GetWindowSurface(window_p)
    if not surface_p:
        print(f"Bugs SDL: SDL_GetWindowSurface failed: {sdl2.SDL_GetError()}",
              flush=True)
        ctrl[0] = 1
        sdl2.SDL_DestroyWindow(window_p)
        sdl2.SDL_Quit()
        sys.exit(1)

    sdl2.SDL_SetSurfaceBlendMode(surface_p, sdl2.SDL_BLENDMODE_NONE)

    surf       = surface_p.contents
    pitch_i32  = surf.pitch // 4
    pixels_ptr = ctypes.cast(surf.pixels, ctypes.POINTER(ctypes.c_int32))
    dst_flat   = np.ctypeslib.as_array(pixels_ptr, shape=(H * pitch_i32,))
    dst        = dst_flat.reshape(H, pitch_i32)

    # Stack probe windows top-down to the left of the main window.
    next_probe_y = 0
    real_title_h = [TITLE_BAR_H]  # mutable so helper can calibrate once

    def _create_probe_window(title_bytes, w, h, label):
        """Create a probe window at (main_x - w, next_probe_y).
        Returns (window_p, surface_p, dst, new_next_y) or (None, None, None, next_probe_y) on failure.
        Calibrates real_title_h from first successfully created window."""
        win = sdl2.SDL_CreateWindow(
            title_bytes,
            main_x - w, next_probe_y,
            w, h,
            sdl2.SDL_WINDOW_SHOWN,
        )
        if not win:
            print(f"Bugs SDL: {label} window creation failed", flush=True)
            return None, None, None, next_probe_y
        actual_y = ctypes.c_int(0)
        sdl2.SDL_GetWindowPosition(win, None, ctypes.byref(actual_y))
        if real_title_h[0] == TITLE_BAR_H:
            top_border = ctypes.c_int(0)
            ret = sdl2.SDL_GetWindowBordersSize(
                win, ctypes.byref(top_border), None, None, None)
            if ret == 0 and top_border.value > 0:
                real_title_h[0] = top_border.value
        new_next_y = actual_y.value + h + real_title_h[0]
        sps = sdl2.SDL_GetWindowSurface(win)
        if not sps:
            sdl2.SDL_DestroyWindow(win)
            return None, None, None, next_probe_y
        sdl2.SDL_SetSurfaceBlendMode(sps, sdl2.SDL_BLENDMODE_NONE)
        surf    = sps.contents
        p_i32   = surf.pitch // 4
        p_ptr   = ctypes.cast(surf.pixels, ctypes.POINTER(ctypes.c_int32))
        flat    = np.ctypeslib.as_array(p_ptr, shape=(h * p_i32,))
        dst_arr = flat.reshape(h, p_i32)
        print(f"Bugs SDL: {label} window created", flush=True)
        return win, sps, dst_arr, new_next_y

    # Stacking order (top → bottom): G, Gq, g, gq.
    # ── G-activity window ────────────────────────────────────────
    G_win_p = G_surf_p = G_dst = None
    if G_activity_shm is not None:
        G_win_p, G_surf_p, G_dst, next_probe_y = _create_probe_window(
            b"G-activity", PROBE_W, ACT_H, "G-activity")

    # ── Gq-activity window (deciles) ─────────────────────────────
    Gq_win_p = Gq_surf_p = Gq_dst = None
    Gq_global_max = 0.0
    if Gq_activity_shm is not None:
        Gq_win_p, Gq_surf_p, Gq_dst, next_probe_y = _create_probe_window(
            b"Gq-activity", PROBE_W, PROBE_H, "Gq-activity")

    # ── g-activity window ────────────────────────────────────────
    g_win_p = g_surf_p = g_dst = None
    if g_activity_shm is not None:
        g_win_p, g_surf_p, g_dst, next_probe_y = _create_probe_window(
            b"g-activity", PROBE_W, ACT_H, "g-activity")

    # ── gq-activity window (deciles) ─────────────────────────────
    gq_win_p = gq_surf_p = gq_dst = None
    gq_global_max = 0.0
    if gq_activity_shm is not None:
        gq_win_p, gq_surf_p, gq_dst, next_probe_y = _create_probe_window(
            b"gq-activity", PROBE_W, PROBE_H, "gq-activity")

    # ── egenome window ───────────────────────────────────────────
    eg_win_p = eg_surf_p = eg_dst = None
    if egenome_shm is not None:
        eg_win_p, eg_surf_p, eg_dst, next_probe_y = _create_probe_window(
            b"egenome (mean +/- std, 9 positions)",
            PROBE_W, PROBE_H, "egenome")

    # ── ts window ────────────────────────────────────────────────
    ts_window_p = ts_surface_p = ts_dst = None
    ts_global_max = 0.0
    if ts_shm is not None:
        ts_window_p, ts_surface_p, ts_dst, next_probe_y = \
            _create_probe_window(b"time series", PROBE_W, PROBE_H, "ts")

    # ── coloring window ─────────────────────────────────────────
    col_window_p = col_surface_p = col_dst = None
    if coloring_shm is not None:
        col_window_p, col_surface_p, col_dst, next_probe_y = \
            _create_probe_window(b"bug coloring",
                                 COLORING_W, COLORING_H, "coloring")

    print("Bugs SDL: entering main loop", flush=True)

    event = sdl2.SDL_Event()

    while ctrl[0] == 0:

        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            if event.type == sdl2.SDL_QUIT:
                ctrl[0] = 1
            elif event.type == sdl2.SDL_KEYDOWN:
                k = event.key.keysym.sym
                if k in (sdl2.SDLK_q, sdl2.SDLK_ESCAPE):
                    ctrl[0] = 1
            elif event.type == sdl2.SDL_WINDOWEVENT:
                if event.window.event == sdl2.SDL_WINDOWEVENT_CLOSE:
                    if event.window.windowID == main_window_id:
                        ctrl[0] = 1

        if ctrl[0]:
            break

        # Main window
        sdl2.SDL_LockSurface(surface_p)
        src = pixels.reshape(N, N)
        if px == 1:
            dst[:N, :N] = src
        else:
            dst[:H, :W] = np.repeat(np.repeat(src, px, axis=0), px, axis=1)
        sdl2.SDL_UnlockSurface(surface_p)
        sdl2.SDL_UpdateWindowSurface(window_p)

        # G-activity window (scroll so newest column is on the right)
        if G_win_p is not None and G_activity_pixels is not None:
            sdl2.SDL_LockSurface(G_surf_p)
            cur = int(G_activity_cursor[0])
            G_dst[:ACT_H, :PROBE_W] = np.roll(G_activity_pixels, -cur, axis=1)
            sdl2.SDL_UnlockSurface(G_surf_p)
            sdl2.SDL_UpdateWindowSurface(G_win_p)

        # g-activity window
        if g_win_p is not None and g_activity_pixels is not None:
            sdl2.SDL_LockSurface(g_surf_p)
            cur = int(g_activity_cursor[0])
            g_dst[:ACT_H, :PROBE_W] = np.roll(g_activity_pixels, -cur, axis=1)
            sdl2.SDL_UnlockSurface(g_surf_p)
            sdl2.SDL_UpdateWindowSurface(g_win_p)

        # Gq-activity window (deciles)
        if Gq_win_p is not None and Gq_activity_deciles is not None:
            sdl2.SDL_LockSurface(Gq_surf_p)
            cur = int(Gq_activity_cursor[0])
            Gq_global_max = _render_q_activity(Gq_dst, Gq_activity_deciles,
                                                cur, Gq_global_max)
            sdl2.SDL_UnlockSurface(Gq_surf_p)
            sdl2.SDL_UpdateWindowSurface(Gq_win_p)

        # gq-activity window (deciles)
        if gq_win_p is not None and gq_activity_deciles is not None:
            sdl2.SDL_LockSurface(gq_surf_p)
            cur = int(gq_activity_cursor[0])
            gq_global_max = _render_q_activity(gq_dst, gq_activity_deciles,
                                                cur, gq_global_max)
            sdl2.SDL_UnlockSurface(gq_surf_p)
            sdl2.SDL_UpdateWindowSurface(gq_win_p)

        # egenome window
        if eg_win_p is not None and egenome_means is not None:
            sdl2.SDL_LockSurface(eg_surf_p)
            cur_eg = int(egenome_cursor[0])
            _render_egenome(eg_dst, egenome_means, egenome_stds, cur_eg)
            sdl2.SDL_UnlockSurface(eg_surf_p)
            sdl2.SDL_UpdateWindowSurface(eg_win_p)

        # ts (time-series) window
        if ts_window_p is not None and ts_traces is not None:
            sdl2.SDL_LockSurface(ts_surface_p)
            cur_ts = int(ts_cursor[0])
            ts_global_max = _render_ts(ts_dst, ts_traces,
                                       cur_ts, ts_global_max)
            sdl2.SDL_UnlockSurface(ts_surface_p)
            sdl2.SDL_UpdateWindowSurface(ts_window_p)

        # coloring window
        if col_window_p is not None and coloring_hist is not None:
            sdl2.SDL_LockSurface(col_surface_p)
            _render_coloring(col_dst, coloring_hist, int(coloring_idx[0]))
            sdl2.SDL_UnlockSurface(col_surface_p)
            sdl2.SDL_UpdateWindowSurface(col_window_p)

        # Window title
        step   = int(ctrl[2])
        mode   = COLOR_MODES[min(int(ctrl[1]), 2)]
        paused = bool(ctrl[4])
        if paused:
            title = f"Bugs  PAUSED  t={step}  color={mode}"
            sdl2.SDL_Delay(16)
        else:
            fps   = ctrl[3] / 10.0
            title = f"Bugs  t={step}  fps={fps:.1f}  color={mode}"
            sdl2.SDL_Delay(4)
        sdl2.SDL_SetWindowTitle(window_p, title.encode())

    print("Bugs SDL: exiting cleanly", flush=True)
    if col_window_p is not None:
        sdl2.SDL_DestroyWindow(col_window_p)
    if ts_window_p is not None:
        sdl2.SDL_DestroyWindow(ts_window_p)
    if eg_win_p is not None:
        sdl2.SDL_DestroyWindow(eg_win_p)
    if gq_win_p is not None:
        sdl2.SDL_DestroyWindow(gq_win_p)
    if Gq_win_p is not None:
        sdl2.SDL_DestroyWindow(Gq_win_p)
    if g_win_p is not None:
        sdl2.SDL_DestroyWindow(g_win_p)
    if G_win_p is not None:
        sdl2.SDL_DestroyWindow(G_win_p)
    sdl2.SDL_DestroyWindow(window_p)
    sdl2.SDL_Quit()
    pixel_shm.close()
    ctrl_shm.close()
    if G_activity_shm is not None:
        G_activity_shm.close()
    if g_activity_shm is not None:
        g_activity_shm.close()
    if Gq_activity_shm is not None:
        Gq_activity_shm.close()
    if gq_activity_shm is not None:
        gq_activity_shm.close()
    if egenome_shm is not None:
        egenome_shm.close()
    if ts_shm is not None:
        ts_shm.close()
    if coloring_shm is not None:
        coloring_shm.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
