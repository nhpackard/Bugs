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
    [1] colormode 0/1/2/3/4
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

# Egenome probe dimensions: narrower window (half PROBE_W), taller
# (three rows) split into 9 horizontal strips (one per Moore position).
EG_W        = PROBE_W // 2
EG_WIN_H    = 3 * PROBE_H
EG_N_POS    = 9
EG_N_Q      = 9
EG_STRIP_H  = EG_WIN_H // EG_N_POS

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
    _c(0xFF44DD44),  # population     - green
    _c(0xFFFFAA22),  # food_bug       - orange
    _c(0xFFFFFF55),  # food_eaten_avg - yellow
    _c(0xFF55BBFF),  # genome_div     - light blue
    _c(0xFFFF77CC),  # io_div         - pink
]
_TS_LABELS = ['pop', 'food_bug', 'food_eaten_avg', 'genome_div', 'io_div']

# 3x5 hand-baked bitmap font — lowercase, digits, and a couple of symbols.
# Each glyph is 5 rows × 3 columns, encoded as 5 ints (top-first, MSB = left).
# Uppercase-style letterforms used even for lowercase keys; descenders are
# approximated within the 5-row box.
_FONT3x5 = {
    'a': (0b010, 0b101, 0b111, 0b101, 0b101),
    'b': (0b110, 0b101, 0b110, 0b101, 0b110),
    'c': (0b011, 0b100, 0b100, 0b100, 0b011),
    'd': (0b110, 0b101, 0b101, 0b101, 0b110),
    'e': (0b111, 0b100, 0b110, 0b100, 0b111),
    'f': (0b111, 0b100, 0b110, 0b100, 0b100),
    'g': (0b011, 0b100, 0b101, 0b101, 0b011),
    'h': (0b101, 0b101, 0b111, 0b101, 0b101),
    'i': (0b111, 0b010, 0b010, 0b010, 0b111),
    'j': (0b001, 0b001, 0b001, 0b101, 0b010),
    'k': (0b101, 0b110, 0b100, 0b110, 0b101),
    'l': (0b100, 0b100, 0b100, 0b100, 0b111),
    'm': (0b101, 0b111, 0b111, 0b101, 0b101),
    'n': (0b101, 0b111, 0b111, 0b111, 0b101),
    'o': (0b010, 0b101, 0b101, 0b101, 0b010),
    'p': (0b110, 0b101, 0b110, 0b100, 0b100),
    'q': (0b010, 0b101, 0b101, 0b011, 0b001),
    'r': (0b110, 0b101, 0b110, 0b110, 0b101),
    's': (0b011, 0b100, 0b010, 0b001, 0b110),
    't': (0b111, 0b010, 0b010, 0b010, 0b010),
    'u': (0b101, 0b101, 0b101, 0b101, 0b010),
    'v': (0b101, 0b101, 0b101, 0b010, 0b010),
    'w': (0b101, 0b101, 0b111, 0b111, 0b101),
    'x': (0b101, 0b101, 0b010, 0b101, 0b101),
    'y': (0b101, 0b101, 0b010, 0b010, 0b010),
    'z': (0b111, 0b001, 0b010, 0b100, 0b111),
    '0': (0b111, 0b101, 0b101, 0b101, 0b111),
    '1': (0b010, 0b110, 0b010, 0b010, 0b111),
    '2': (0b110, 0b001, 0b010, 0b100, 0b111),
    '3': (0b110, 0b001, 0b010, 0b001, 0b110),
    '4': (0b101, 0b101, 0b111, 0b001, 0b001),
    '5': (0b111, 0b100, 0b110, 0b001, 0b110),
    '6': (0b011, 0b100, 0b110, 0b101, 0b010),
    '7': (0b111, 0b001, 0b010, 0b100, 0b100),
    '8': (0b010, 0b101, 0b010, 0b101, 0b010),
    '9': (0b010, 0b101, 0b011, 0b001, 0b110),
    '_': (0b000, 0b000, 0b000, 0b000, 0b111),
    '/': (0b001, 0b001, 0b010, 0b100, 0b100),
    ' ': (0b000, 0b000, 0b000, 0b000, 0b000),
    '-': (0b000, 0b000, 0b111, 0b000, 0b000),
    '.': (0b000, 0b000, 0b000, 0b000, 0b010),
}


def _draw_text(dst, x, y, text, color):
    """Write `text` into int32 ARGB buffer `dst` at (x, y) in the given color.
    One pixel per glyph dot (no scaling). Unknown characters render as blanks."""
    for ci, ch in enumerate(text):
        glyph = _FONT3x5.get(ch.lower(), _FONT3x5[' '])
        gx = x + ci * 4  # 3-wide + 1 px inter-glyph gap
        for row, bits in enumerate(glyph):
            gy = y + row
            if gy < 0 or gy >= dst.shape[0]:
                continue
            if bits & 0b100 and 0 <= gx     < dst.shape[1]:
                dst[gy, gx]     = color
            if bits & 0b010 and 0 <= gx + 1 < dst.shape[1]:
                dst[gy, gx + 1] = color
            if bits & 0b001 and 0 <= gx + 2 < dst.shape[1]:
                dst[gy, gx + 2] = color


def _draw_ts_legend(dst):
    """Draw a small legend in the upper-left of the ts probe window:
    one row per trace (swatch + label) stacked vertically."""
    pad_x = 3
    pad_y = 3
    row_h = 7          # 5 px glyph + 2 px gap
    sw_w  = 4          # swatch width
    sw_h  = 4          # swatch height
    gap   = 3          # gap between swatch and text
    for ti, label in enumerate(_TS_LABELS):
        y = pad_y + ti * row_h
        if y + 5 >= dst.shape[0]:
            break
        col = _TS_COLORS[ti % len(_TS_COLORS)]
        dst[y:y + sw_h, pad_x:pad_x + sw_w] = col
        _draw_text(dst, pad_x + sw_w + gap, y, label, col)

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
    """Render scalar time-series with per-trace linear auto-scaling.

    Each trace's observed [min, max] over the visible window maps to the
    middle 80% of the strip height (10% padding top and bottom). Zero
    samples are treated as "uninitialized / pop=0" and excluded from both
    autoscale and plotting.

    trace_bufs: list of float32[PROBE_W] ring buffers.
    global_max: unused (kept for signature compatibility with caller).
    """
    import numpy as np

    dst[:PROBE_H, :PROBE_W] = BG_COLOR

    xs = np.arange(PROBE_W)
    y_top = 0.1 * (PROBE_H - 1)
    y_bot = 0.9 * (PROBE_H - 1)
    H_grid = np.arange(PROBE_H)[:, None]            # (H, 1)

    for ti, b in enumerate(trace_bufs):
        r = np.roll(b, -cursor)
        mask = r > 0
        if not mask.any():
            continue
        vals = r[mask]
        lo = float(vals.min())
        hi = float(vals.max())
        if hi <= lo:
            ys_valid = np.full(int(mask.sum()),
                               int((y_top + y_bot) * 0.5), dtype=np.int32)
        else:
            scale = (y_bot - y_top) / (hi - lo)
            ys_valid = np.clip(
                (y_bot - (vals - lo) * scale).astype(np.int32),
                0, PROBE_H - 1)

        # Scatter ys over the full x range; -1 marks invalid columns.
        ys = np.full(PROBE_W, -1, dtype=np.int32)
        ys[mask] = ys_valid

        # Draw line segments: for each column x where both x-1 and x are
        # valid, fill the vertical span between y[x-1] and y[x] so the
        # trace reads as a connected line rather than sparse dots.
        prev_ys = np.roll(ys, 1)
        prev_ys[0] = -1
        both = (ys >= 0) & (prev_ys >= 0)
        y_lo = np.minimum(ys, prev_ys)
        y_hi = np.maximum(ys, prev_ys)
        fill = ((H_grid >= y_lo[None, :])
                & (H_grid <= y_hi[None, :])
                & both[None, :])

        col = _TS_COLORS[ti % len(_TS_COLORS)]
        dst[fill] = col
        # Isolated points (neighbor invalid) still draw as a single pixel.
        isolated = mask & ~both
        dst[ys[isolated], xs[isolated]] = col

    dst[:PROBE_H, PROBE_W - 1] = CURSOR_COLOR
    _draw_ts_legend(dst)
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


def _render_egenome(dst, q_view, cursor):
    """Render the egenome probe as 9 stacked strips (one per Moore position).

    q_view : ndarray (9 positions, 9 quantiles, EG_W) float32 — each
             column is the quantile vector for one time step. Quantiles
             are p10, p20, …, p90 in order along axis 1.

    Each strip shows 8 bands between consecutive quantiles; brightness is
    inversely proportional to band span (narrow = bright, wide = dim),
    giving a density-shaded approximation of the population distribution.
    A white line traces the median (p50). Bands use the position's palette
    color; empty (all-zero) columns render as background.
    """
    import numpy as np

    dst[:EG_WIN_H, :EG_W] = BG_COLOR

    xs = np.arange(EG_W, dtype=np.int32)
    ys_strip = np.arange(EG_STRIP_H, dtype=np.int32)
    # Value at each pixel row of one strip: y=0 → 1.0, y=H-1 → 0.0.
    strip_vals = 1.0 - ys_strip.astype(np.float32) / max(EG_STRIP_H - 1, 1)

    for p in range(EG_N_POS):
        strip_y0 = p * EG_STRIP_H
        strip_y1 = strip_y0 + EG_STRIP_H

        qs = np.roll(q_view[p], -cursor, axis=1)     # (9, EG_W)
        valid = (qs > 0).any(axis=0)
        if not valid.any():
            continue

        # Per-position adaptive reference: typical inter-quantile span,
        # so brightness is normalized against the position's own baseline
        # rather than a global constant. Uses the *median* of non-zero
        # spans so that (a) zero-span bands from peggings at 0/1 don't
        # drag ref_span to 0, and (b) a single very narrow band (e.g.,
        # 0.003 between a pegged p10 and a nearly-pegged p20) doesn't
        # dominate via the low percentile and dim the rest of the strip.
        spans = np.diff(qs, axis=0)                  # (8, EG_W) band spans
        nz_spans = spans[:, valid]
        nz_spans = nz_spans[nz_spans > 1e-6]
        if nz_spans.size == 0:
            ref_span = 1.0 / EG_N_Q
        else:
            ref_span = float(np.median(nz_spans))
            if ref_span < 1e-4:
                ref_span = 1e-4

        cr, cg, cb = _EG_RGB[p]

        # Float workspace for this strip so bands compose cleanly.
        bg = int(BG_COLOR) & 0xFFFFFFFF
        br = float((bg >> 16) & 0xFF)
        bg_g = float((bg >>  8) & 0xFF)
        bb = float(bg & 0xFF)
        work_r = np.full((EG_STRIP_H, EG_W), br,  dtype=np.float32)
        work_g = np.full((EG_STRIP_H, EG_W), bg_g, dtype=np.float32)
        work_b = np.full((EG_STRIP_H, EG_W), bb,  dtype=np.float32)

        # Vectorized band membership: for each pixel, which band (0..8)
        # does its value fall into? Count of quantiles below it.
        # cmp shape: (9, EG_STRIP_H, EG_W) — broadcasts qs (9, 1, EG_W)
        # against strip_vals (EG_STRIP_H, EG_W).
        qs_b = qs[:, None, :]                          # (9, 1, EG_W)
        vals = strip_vals[None, :, None]               # (1, H, 1)
        # band_idx[y, x] in 0..9. 0 = below p10, 9 = above p90.
        band_idx = (qs_b < vals).sum(axis=0)           # (EG_STRIP_H, EG_W)

        for k in range(EG_N_Q - 1):                    # k = 0..7
            band_mask = (band_idx == k + 1)            # inside (q_k, q_{k+1}]
            if not band_mask.any():
                continue
            # Per-column brightness = ref_span / this column's band span.
            col_span = spans[k]                        # (EG_W,)
            with np.errstate(divide='ignore', invalid='ignore'):
                bright = np.where(col_span > 1e-6,
                                  ref_span / col_span, 1.0)
            bright = np.clip(bright, 0.0, 1.0).astype(np.float32)
            bright2d = np.broadcast_to(bright[None, :],
                                       (EG_STRIP_H, EG_W))
            m = band_mask
            alpha = bright2d[m]                         # per-pixel alpha
            work_r[m] = work_r[m] * (1.0 - alpha) + cr * alpha
            work_g[m] = work_g[m] * (1.0 - alpha) + cg * alpha
            work_b[m] = work_b[m] * (1.0 - alpha) + cb * alpha

        # Median line: p50 is quantile index 4. Overlay in white.
        m_vals = qs[4]
        med_y = np.clip(
            ((1.0 - np.clip(m_vals, 0.0, 1.0)) * (EG_STRIP_H - 1)).astype(np.int32),
            0, EG_STRIP_H - 1)
        work_r[med_y[valid], xs[valid]] = 255.0
        work_g[med_y[valid], xs[valid]] = 255.0
        work_b[med_y[valid], xs[valid]] = 255.0

        # Pack to ARGB int32 and splat into dst strip.
        r = np.clip(work_r, 0, 255).astype(np.uint32)
        g = np.clip(work_g, 0, 255).astype(np.uint32)
        b = np.clip(work_b, 0, 255).astype(np.uint32)
        argb = (0xFF000000 | (r << 16) | (g << 8) | b).astype(np.int64)
        argb = np.where(argb < 0x80000000, argb,
                        argb - 0x100000000).astype(np.int32)
        dst[strip_y0:strip_y1, :EG_W] = argb

        # Faint horizontal separator between strips (except above strip 0).
        if p > 0:
            dst[strip_y0, :EG_W] = CURSOR_COLOR

    # 3x3 Moore-neighborhood legend in upper-left.
    _draw_egenome_template(dst)

    # Cursor marker (rightmost column).
    dst[:EG_WIN_H, EG_W - 1] = CURSOR_COLOR


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

    # ── Egenome shared memory (9 positions × 9 quantiles × EG_W) ───
    egenome_shm     = None
    egenome_cursor  = None
    egenome_q       = None
    if egenome_shm_name:
        try:
            egenome_shm = SharedMemory(name=egenome_shm_name)
            egenome_cursor = np.ndarray((1,), dtype=np.int32,
                                        buffer=egenome_shm.buf)
            egenome_q = np.ndarray(
                (EG_N_POS, EG_N_Q, EG_W), dtype=np.float32,
                buffer=egenome_shm.buf, offset=4)
            print(f"Bugs SDL: egenome shm opened "
                  f"({EG_N_POS}x{EG_N_Q}x{EG_W} quantiles)", flush=True)
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

    COLOR_MODES = ["red-bugs", "genome-hash", "bug-food", "bug-age",
                   "lineage"]

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
            b"egenome (9 positions, quantile bands)",
            EG_W, EG_WIN_H, "egenome")

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
        if eg_win_p is not None and egenome_q is not None:
            sdl2.SDL_LockSurface(eg_surf_p)
            cur_eg = int(egenome_cursor[0])
            _render_egenome(eg_dst, egenome_q, cur_eg)
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
        mode   = COLOR_MODES[min(int(ctrl[1]), len(COLOR_MODES) - 1)]
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
