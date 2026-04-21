"""
sdl_worker.py — SDL2 display subprocess for Bugs.

Launched by controls.run_with_controls() via subprocess.Popen.
All output goes to the terminal where Jupyter was started.

Usage (internal):
    python sdl_worker.py <pixel_shm> <ctrl_shm> <N> <px> \\
                         [--activity=<shm>] [--q-activity=<shm>] \\
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


def main():
    if len(sys.argv) < 5:
        print("Bugs SDL: bad args", flush=True)
        sys.exit(1)

    pixel_shm_name = sys.argv[1]
    ctrl_shm_name  = sys.argv[2]
    N  = int(sys.argv[3])
    px = int(sys.argv[4])
    W, H = N * px, N * px

    activity_shm_name   = None
    q_activity_shm_name = None
    ts_shm_name         = None
    coloring_shm_name   = None
    for arg in sys.argv[5:]:
        if arg.startswith("--activity="):
            activity_shm_name = arg[len("--activity="):]
        elif arg.startswith("--q-activity="):
            q_activity_shm_name = arg[len("--q-activity="):]
        elif arg.startswith("--ts="):
            ts_shm_name = arg[len("--ts="):]
        elif arg.startswith("--coloring="):
            coloring_shm_name = arg[len("--coloring="):]

    ACT_H = 2 * PROBE_H  # 256

    print(f"Bugs SDL: starting  N={N} px={px}  "
          f"activity={bool(activity_shm_name)}  "
          f"q_activity={bool(q_activity_shm_name)}  "
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

    # ── Activity shared memory ───────────────────────────────────
    activity_shm     = None
    activity_cursor  = None
    activity_pixels  = None
    if activity_shm_name:
        try:
            activity_shm = SharedMemory(name=activity_shm_name)
            activity_cursor = np.ndarray((1,), dtype=np.int32,
                                         buffer=activity_shm.buf)
            activity_pixels = np.ndarray((ACT_H, PROBE_W), dtype=np.int32,
                                         buffer=activity_shm.buf, offset=4)
            print(f"Bugs SDL: activity shm opened ({ACT_H}x{PROBE_W})",
                  flush=True)
        except Exception as e:
            print(f"Bugs SDL: activity SharedMemory open failed: {e}",
                  flush=True)
            activity_shm_name = None

    # ── q_activity shared memory ─────────────────────────────────
    QA_N_DECILES        = 9
    q_activity_shm      = None
    q_activity_cursor   = None
    q_activity_deciles  = None
    if q_activity_shm_name:
        try:
            q_activity_shm = SharedMemory(name=q_activity_shm_name)
            q_activity_cursor = np.ndarray((1,), dtype=np.int32,
                                            buffer=q_activity_shm.buf)
            q_activity_deciles = []
            off = 4
            for _ in range(QA_N_DECILES):
                q_activity_deciles.append(
                    np.ndarray((PROBE_W,), dtype=np.float32,
                               buffer=q_activity_shm.buf, offset=off))
                off += PROBE_W * 4
            print(f"Bugs SDL: q_activity shm opened ({QA_N_DECILES}x{PROBE_W})",
                  flush=True)
        except Exception as e:
            print(f"Bugs SDL: q_activity SharedMemory open failed: {e}",
                  flush=True)
            q_activity_shm_name = None

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
    real_title_h = TITLE_BAR_H

    # ── Activity window ──────────────────────────────────────────
    act_window_p  = None
    act_surface_p = None
    act_dst       = None
    if activity_shm is not None:
        aw_x = main_x - PROBE_W
        aw = sdl2.SDL_CreateWindow(
            b"activity",
            aw_x, next_probe_y,
            PROBE_W, ACT_H,
            sdl2.SDL_WINDOW_SHOWN,
        )
        if aw:
            actual_y = ctypes.c_int(0)
            sdl2.SDL_GetWindowPosition(aw, None, ctypes.byref(actual_y))
            top_border = ctypes.c_int(0)
            ret = sdl2.SDL_GetWindowBordersSize(
                aw, ctypes.byref(top_border), None, None, None)
            if ret == 0 and top_border.value > 0:
                real_title_h = top_border.value
            next_probe_y = actual_y.value + ACT_H + real_title_h
            aps = sdl2.SDL_GetWindowSurface(aw)
            if aps:
                sdl2.SDL_SetSurfaceBlendMode(aps, sdl2.SDL_BLENDMODE_NONE)
                asurf   = aps.contents
                ap_i32  = asurf.pitch // 4
                ap_ptr  = ctypes.cast(asurf.pixels,
                                      ctypes.POINTER(ctypes.c_int32))
                ad_flat = np.ctypeslib.as_array(ap_ptr,
                                                shape=(ACT_H * ap_i32,))
                act_dst       = ad_flat.reshape(ACT_H, ap_i32)
                act_window_p  = aw
                act_surface_p = aps
                print("Bugs SDL: activity window created", flush=True)
            else:
                sdl2.SDL_DestroyWindow(aw)
        else:
            print("Bugs SDL: activity window creation failed", flush=True)

    # ── q_activity window ────────────────────────────────────────
    qa_window_p    = None
    qa_surface_p   = None
    qa_dst         = None
    qa_global_max  = 0.0
    if q_activity_shm is not None:
        qaw_x = main_x - PROBE_W
        qaw = sdl2.SDL_CreateWindow(
            b"q_activity",
            qaw_x, next_probe_y,
            PROBE_W, PROBE_H,
            sdl2.SDL_WINDOW_SHOWN,
        )
        if qaw:
            actual_y = ctypes.c_int(0)
            sdl2.SDL_GetWindowPosition(qaw, None, ctypes.byref(actual_y))
            if act_window_p is None:
                top_border = ctypes.c_int(0)
                ret = sdl2.SDL_GetWindowBordersSize(
                    qaw, ctypes.byref(top_border), None, None, None)
                if ret == 0 and top_border.value > 0:
                    real_title_h = top_border.value
            next_probe_y = actual_y.value + PROBE_H + real_title_h
            qaps = sdl2.SDL_GetWindowSurface(qaw)
            if qaps:
                sdl2.SDL_SetSurfaceBlendMode(qaps, sdl2.SDL_BLENDMODE_NONE)
                qasurf  = qaps.contents
                qap_i32 = qasurf.pitch // 4
                qap_ptr = ctypes.cast(qasurf.pixels,
                                       ctypes.POINTER(ctypes.c_int32))
                qad_flat = np.ctypeslib.as_array(qap_ptr,
                                                  shape=(PROBE_H * qap_i32,))
                qa_dst       = qad_flat.reshape(PROBE_H, qap_i32)
                qa_window_p  = qaw
                qa_surface_p = qaps
                print("Bugs SDL: q_activity window created", flush=True)
            else:
                sdl2.SDL_DestroyWindow(qaw)
        else:
            print("Bugs SDL: q_activity window creation failed", flush=True)

    # ── ts window ────────────────────────────────────────────────
    ts_window_p   = None
    ts_surface_p  = None
    ts_dst        = None
    ts_global_max = 0.0
    if ts_shm is not None:
        tsw_x = main_x - PROBE_W
        tsw = sdl2.SDL_CreateWindow(
            b"time series",
            tsw_x, next_probe_y,
            PROBE_W, PROBE_H,
            sdl2.SDL_WINDOW_SHOWN,
        )
        if tsw:
            actual_y = ctypes.c_int(0)
            sdl2.SDL_GetWindowPosition(tsw, None, ctypes.byref(actual_y))
            next_probe_y = actual_y.value + PROBE_H + real_title_h
            tsps = sdl2.SDL_GetWindowSurface(tsw)
            if tsps:
                sdl2.SDL_SetSurfaceBlendMode(tsps, sdl2.SDL_BLENDMODE_NONE)
                tssurf  = tsps.contents
                tsp_i32 = tssurf.pitch // 4
                tsp_ptr = ctypes.cast(tssurf.pixels,
                                      ctypes.POINTER(ctypes.c_int32))
                tsd_flat = np.ctypeslib.as_array(tsp_ptr,
                                                 shape=(PROBE_H * tsp_i32,))
                ts_dst       = tsd_flat.reshape(PROBE_H, tsp_i32)
                ts_window_p  = tsw
                ts_surface_p = tsps
                print("Bugs SDL: ts window created", flush=True)
            else:
                sdl2.SDL_DestroyWindow(tsw)
        else:
            print("Bugs SDL: ts window creation failed", flush=True)

    # ── coloring window ─────────────────────────────────────────
    col_window_p  = None
    col_surface_p = None
    col_dst       = None
    if coloring_shm is not None:
        cw_x = main_x - COLORING_W
        cw = sdl2.SDL_CreateWindow(
            b"bug coloring",
            cw_x, next_probe_y,
            COLORING_W, COLORING_H,
            sdl2.SDL_WINDOW_SHOWN,
        )
        if cw:
            actual_y = ctypes.c_int(0)
            sdl2.SDL_GetWindowPosition(cw, None, ctypes.byref(actual_y))
            next_probe_y = actual_y.value + COLORING_H + real_title_h
            cps = sdl2.SDL_GetWindowSurface(cw)
            if cps:
                sdl2.SDL_SetSurfaceBlendMode(cps, sdl2.SDL_BLENDMODE_NONE)
                csurf  = cps.contents
                cp_i32 = csurf.pitch // 4
                cp_ptr = ctypes.cast(csurf.pixels,
                                     ctypes.POINTER(ctypes.c_int32))
                cd_flat = np.ctypeslib.as_array(cp_ptr,
                                                shape=(COLORING_H * cp_i32,))
                col_dst       = cd_flat.reshape(COLORING_H, cp_i32)
                col_window_p  = cw
                col_surface_p = cps
                print("Bugs SDL: coloring window created", flush=True)
            else:
                sdl2.SDL_DestroyWindow(cw)
        else:
            print("Bugs SDL: coloring window creation failed", flush=True)

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

        # Activity window (scroll so newest column is on the right)
        if act_window_p is not None and activity_pixels is not None:
            sdl2.SDL_LockSurface(act_surface_p)
            cur_act = int(activity_cursor[0])
            act_dst[:ACT_H, :PROBE_W] = np.roll(activity_pixels, -cur_act,
                                                  axis=1)
            sdl2.SDL_UnlockSurface(act_surface_p)
            sdl2.SDL_UpdateWindowSurface(act_window_p)

        # q_activity window
        if qa_window_p is not None and q_activity_deciles is not None:
            sdl2.SDL_LockSurface(qa_surface_p)
            cur_qa = int(q_activity_cursor[0])
            qa_global_max = _render_q_activity(qa_dst, q_activity_deciles,
                                                cur_qa, qa_global_max)
            sdl2.SDL_UnlockSurface(qa_surface_p)
            sdl2.SDL_UpdateWindowSurface(qa_window_p)

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
    if qa_window_p is not None:
        sdl2.SDL_DestroyWindow(qa_window_p)
    if act_window_p is not None:
        sdl2.SDL_DestroyWindow(act_window_p)
    sdl2.SDL_DestroyWindow(window_p)
    sdl2.SDL_Quit()
    pixel_shm.close()
    ctrl_shm.close()
    if activity_shm is not None:
        activity_shm.close()
    if q_activity_shm is not None:
        q_activity_shm.close()
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
