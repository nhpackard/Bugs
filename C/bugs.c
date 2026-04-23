#include "bugs.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <math.h>

/* ── xorshift64* PRNG ──────────────────────────────────────────────── */

static uint64_t g_rng = 0x12345678deadbeefULL;

static inline uint64_t rng_next64(void)
{
    uint64_t x = g_rng;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    g_rng = x;
    return x * 0x2545F4914F6CDD1DULL;
}

static inline uint32_t rng_u32(void)    { return (uint32_t)rng_next64(); }
static inline float    rng_uniform(void) /* [0, 1) */
    { return (float)(rng_u32() & 0x00FFFFFFu) * (1.0f / (float)(1u << 24)); }
static inline int      rng_int(int n)    { return (int)(rng_u32() % (uint32_t)n); }

/* Standard normal N(0,1) via Box-Muller. Second variate discarded. */
static inline float rng_gauss(void)
{
    float u1 = rng_uniform();
    float u2 = rng_uniform();
    if (u1 < 1e-7f) u1 = 1e-7f;
    return sqrtf(-2.0f * logf(u1)) * cosf(2.0f * (float)M_PI * u2);
}

void bugs_set_seed(uint64_t s)
{
    if (s == 0) s = (uint64_t)time(NULL) ^ 0xA5A5A5A5DEADBEEFULL;
    g_rng = s;
}

/* ── Gene / bug structs ────────────────────────────────────────────── */

typedef struct {
    int8_t  dx;
    int8_t  dy;
    uint8_t mag;   /* 1..15 */
    uint8_t dir;   /* 0..7  (quad<<1 | diag) */
} gene_t;

/* A full genome: 32 genes.  Used as the hash key for activity tracking. */
typedef struct {
    gene_t genes[N_GENES];
} genome_t;

typedef struct {
    genome_t genome;
    float    egenome[EGENOME_N]; /* per-position food thresholds (bug's perception) */
    float    food;
    int32_t  age;
    int32_t  x;
    int32_t  y;
    uint32_t genome_hash;  /* FNV-1a over genome bytes (does not include egenome) */
    uint32_t lineage_color;/* ARGB; random at seed, inherited unchanged on birth */
    uint8_t  alive;
    uint8_t  born_this_step;
} bug_t;

/* ── Grid / global state ───────────────────────────────────────────── */

static int      gN        = 0;
static uint32_t g_step    = 0;

/* meta-params */
static float g_mutation_rate    = 0.02f;
static float g_reproduction_food = 20.0f;
static float g_movement_cost    = 0.5f;   /* positive: food lost per tick */
static float g_eat_amount       = 2.0f;
static float g_initial_food     = 10.0f;
static float g_food_inc         = 0.01f;
static int   g_gdiff            = 0;
static int   g_move_range       = MAG_MAX;  /* 1..MAG_MAX; caps random_gene magnitude */
static float g_mu_egenome       = 0.0f;     /* σ of per-entry Gaussian mutation on birth */

/* Per-position food-threshold vector used to initialize a new bug's
 * egenome on seeding (bugs_seed_with_density). Positions NW..SE in
 * reading order: [0..8]. Defaults to 0.1 on all nine entries, matching
 * the previous scalar food_threshold=0.1. */
static float g_egenome_init[EGENOME_N] = {
    0.1f, 0.1f, 0.1f,
    0.1f, 0.1f, 0.1f,
    0.1f, 0.1f, 0.1f,
};

/* lattice fields */
static float   *F_food   = NULL;   /* [N*N] live food */
static float   *F_src    = NULL;   /* [N*N] regeneration target */
static float   *F_temp   = NULL;   /* [N*N] scratch for diffusion */
static int32_t *bug_at   = NULL;   /* [N*N]  -1 if empty, else bug index */
static uint8_t *bug_mask = NULL;   /* [N*N]  1 if bug present (for colorize) */

/* bug pool: contiguous, with a free-list of dead slots */
static bug_t   *bug_pool  = NULL;
static int32_t *alive_ids = NULL;   /* [pool_cap] indices of alive bugs */
static int32_t *free_ids  = NULL;   /* [pool_cap] free slots in pool */
static int      pool_cap  = 0;
static int      n_alive   = 0;
static int      n_free    = 0;

/* stats */
static int  g_births_last = 0;
static int  g_deaths_last = 0;
static float g_food_bug   = 0.0f;   /* running Σ of alive-bug food */
static float g_food_eaten_last = 0.0f;  /* total food eaten during last bugs_step */

/* Smoothed running max of bug ages, driving the bug-age colormode's
 * autoscale. Fast-up / slow-down: jumps to any new observed max, decays
 * slowly otherwise. Reset on bugs_init / bugs_exterminate. */
static double g_age_scale = 50.0;

/* ── Forward declarations ──────────────────────────────────────────── */

static void act_reset(void);
static void act_free_all(void);
static void gact_reset(void);
static void gact_free_all(void);

/* ── Pool helpers ──────────────────────────────────────────────────── */

static void pool_grow(int new_cap)
{
    int old_cap = pool_cap;
    bug_pool  = realloc(bug_pool,  (size_t)new_cap * sizeof(bug_t));
    alive_ids = realloc(alive_ids, (size_t)new_cap * sizeof(int32_t));
    free_ids  = realloc(free_ids,  (size_t)new_cap * sizeof(int32_t));
    /* Push new slots onto free list in descending order so pool_alloc
     * pops them in ascending order (LIFO stack, better locality). */
    for (int i = new_cap - 1; i >= old_cap; i--) {
        memset(&bug_pool[i], 0, sizeof(bug_t));
        bug_pool[i].alive = 0;
        free_ids[n_free++] = i;
    }
    pool_cap = new_cap;
}

static int32_t pool_alloc(void)
{
    if (n_free == 0) pool_grow(pool_cap == 0 ? 128 : pool_cap * 2);
    return free_ids[--n_free];
}

static void pool_release(int32_t idx)
{
    bug_pool[idx].alive = 0;
    free_ids[n_free++] = idx;
}

/* ── Indexing helpers ──────────────────────────────────────────────── */

static inline int wrap(int v, int n) { return ((v % n) + n) % n; }
static inline int gidx(int x, int y) { return wrap(y, gN) * gN + wrap(x, gN); }

/* ── Gene generation / mutation ────────────────────────────────────── */

/* Random gene: uniform over {1..g_move_range} magnitude × {0..3} quadrant × {0..1} diagonal.
 * g_move_range=1 collapses the move space to the 8 Moore neighbors;
 * g_move_range=MAG_MAX (15) is the full 8×15 = 120-move space. */
static gene_t random_gene(void)
{
    gene_t g;
    int mag  = rng_int(g_move_range) + 1;  /* 1..g_move_range */
    int diag = rng_int(2);              /* 0 or 1 */
    int quad = rng_int(4);              /* 0..3 */
    switch (quad) {
    case 0: g.dx =  (int8_t)mag;         g.dy = (int8_t)(mag * diag);   break;
    case 1: g.dx = (int8_t)(-mag * diag); g.dy =  (int8_t)mag;          break;
    case 2: g.dx = (int8_t)(-mag);        g.dy = (int8_t)(-mag * diag); break;
    default:g.dx = (int8_t)(mag * diag);  g.dy = (int8_t)(-mag);        break;
    }
    g.mag = (uint8_t)mag;
    g.dir = (uint8_t)((quad << 1) | diag);
    return g;
}

static void genome_random(genome_t *g)
{
    for (int i = 0; i < N_GENES; i++)
        g->genes[i] = random_gene();
}

/* Per-gene copy with mutation rate r. */
static void genome_mutate_copy(const genome_t *src, genome_t *dst, float r)
{
    for (int i = 0; i < N_GENES; i++) {
        if (rng_uniform() < r)
            dst->genes[i] = random_gene();
        else
            dst->genes[i] = src->genes[i];
    }
}

/* Per-position copy with truncated-Gaussian drift (σ = sigma), clipped to
 * [0, 1]. When sigma == 0 this degenerates to a plain copy. */
static void egenome_mutate_copy(const float *src, float *dst, float sigma)
{
    for (int i = 0; i < EGENOME_N; i++) {
        float v = src[i];
        if (sigma > 0.0f) v += sigma * rng_gauss();
        if (v < 0.0f) v = 0.0f;
        if (v > 1.0f) v = 1.0f;
        dst[i] = v;
    }
}

/* FNV-1a over the genome byte sequence (N_GENES * 4 = 128 bytes). */
static uint32_t genome_hash_fn(const genome_t *g)
{
    const uint8_t *b = (const uint8_t *)g;
    uint32_t h = 0x811c9dc5u;
    for (int i = 0; i < (int)sizeof(genome_t); i++) {
        h ^= b[i];
        h *= 0x01000193u;
    }
    if (h == 0) h = 1; /* reserve 0 as empty sentinel in hash table */
    return h;
}

static int32_t hash_to_color(uint32_t h)
{
    return (int32_t)(0xFF000000u | (h & 0x00FFFFFFu));
}

/* Murmur3 32-bit finalizer. Spreads structured keys (e.g. g-activity's
 * packed (nbhd, dx, dy)) across the low 24 bits before colorizing, so
 * neighboring keys don't collapse to near-identical shades. */
static inline uint32_t mix32(uint32_t k)
{
    k ^= k >> 16;
    k *= 0x85ebca6bu;
    k ^= k >> 13;
    k *= 0xc2b2ae35u;
    k ^= k >> 16;
    return k;
}

/* ── Lifecycle ─────────────────────────────────────────────────────── */

void bugs_init(int N)
{
    bugs_free();
    gN = N;
    size_t cells = (size_t)N * (size_t)N;
    F_food   = calloc(cells, sizeof(float));
    F_src    = calloc(cells, sizeof(float));
    F_temp   = calloc(cells, sizeof(float));
    bug_at   = malloc(cells * sizeof(int32_t));
    bug_mask = calloc(cells, sizeof(uint8_t));
    for (size_t i = 0; i < cells; i++) bug_at[i] = -1;

    pool_grow(1024);
    n_alive = 0;
    n_free  = 0;

    g_step = 0;
    g_births_last = g_deaths_last = 0;
    g_food_bug    = 0.0f;
    g_food_eaten_last = 0.0f;
    g_age_scale   = 50.0;

    act_reset();
    gact_reset();
}

void bugs_free(void)
{
    free(F_food);   F_food   = NULL;
    free(F_src);    F_src    = NULL;
    free(F_temp);   F_temp   = NULL;
    free(bug_at);   bug_at   = NULL;
    free(bug_mask); bug_mask = NULL;
    free(bug_pool); bug_pool = NULL;
    free(alive_ids); alive_ids = NULL;
    free(free_ids);  free_ids  = NULL;
    pool_cap = n_alive = n_free = 0;
    gN = 0;
    act_free_all();
    gact_free_all();
}

/* ── Parameter setters ─────────────────────────────────────────────── */

void bugs_set_mutation_rate(float r)     { g_mutation_rate    = r; }
void bugs_set_reproduction_food(float t) { g_reproduction_food = t; }
void bugs_set_movement_cost(float c)     { g_movement_cost    = c; }
void bugs_set_eat_amount(float a)        { g_eat_amount       = a; }
void bugs_set_initial_food(float f)      { g_initial_food     = f; }
void bugs_set_food_inc(float i)          { g_food_inc         = i; }
void bugs_set_gdiff(int d)               { g_gdiff            = d; }
void bugs_set_mu_egenome(float s)        { g_mu_egenome       = s < 0.0f ? 0.0f : s; }

void bugs_set_egenome_init(const float *v)
{
    for (int i = 0; i < EGENOME_N; i++) {
        float x = v[i];
        if (x < 0.0f) x = 0.0f;
        if (x > 1.0f) x = 1.0f;
        g_egenome_init[i] = x;
    }
}

void bugs_get_egenome_init(float *out)
{
    for (int i = 0; i < EGENOME_N; i++) out[i] = g_egenome_init[i];
}
void bugs_set_move_range(int r)
{
    if (r < 1)        r = 1;
    if (r > MAG_MAX)  r = MAG_MAX;
    g_move_range = r;
}

float bugs_get_mutation_rate(void)     { return g_mutation_rate; }
float bugs_get_reproduction_food(void) { return g_reproduction_food; }
float bugs_get_movement_cost(void)     { return g_movement_cost; }
float bugs_get_eat_amount(void)        { return g_eat_amount; }
float bugs_get_initial_food(void)      { return g_initial_food; }
float bugs_get_food_inc(void)          { return g_food_inc; }
int   bugs_get_gdiff(void)             { return g_gdiff; }
int   bugs_get_move_range(void)        { return g_move_range; }
float bugs_get_mu_egenome(void)        { return g_mu_egenome; }

/* ── Food field setup ──────────────────────────────────────────────── */

void bugs_set_food_source(const float *src)
{
    size_t cells = (size_t)gN * gN;
    memcpy(F_src,  src, cells * sizeof(float));
    memcpy(F_food, src, cells * sizeof(float));
}

void bugs_set_food_source_from_brightness(const float *brightness, float thresh)
{
    size_t cells = (size_t)gN * gN;
    for (size_t i = 0; i < cells; i++) {
        float v = (brightness[i] < thresh) ? 1.0f : 0.0f;
        F_src[i]  = v;
        F_food[i] = v;
    }
}

/* ── Seeding ───────────────────────────────────────────────────────── */

static void place_bug_at(int32_t bid, int x, int y)
{
    int idx = gidx(x, y);
    bug_pool[bid].x = wrap(x, gN);
    bug_pool[bid].y = wrap(y, gN);
    bug_at[idx]   = bid;
    bug_mask[idx] = 1;
}

/* Attempt to place bug at (x,y); if occupied, try random Moore-neighbor bumps.
 * Bounded iterations; on failure, silently scan for the first free cell. */
static void place_or_bump(int32_t bid, int x, int y)
{
    for (int tries = 0; tries < 64; tries++) {
        int cx = wrap(x, gN);
        int cy = wrap(y, gN);
        int idx = cy * gN + cx;
        if (bug_at[idx] == -1) {
            place_bug_at(bid, cx, cy);
            return;
        }
        x += rng_int(3) - 1;
        y += rng_int(3) - 1;
    }
    /* fallback: linear scan */
    for (int i = 0; i < gN * gN; i++) {
        if (bug_at[i] == -1) {
            place_bug_at(bid, i % gN, i / gN);
            return;
        }
    }
    /* world is full — drop the bug (shouldn't happen for reasonable densities) */
    pool_release(bid);
}

void bugs_exterminate(void)
{
    size_t cells = (size_t)gN * gN;
    for (size_t i = 0; i < cells; i++) { bug_at[i] = -1; bug_mask[i] = 0; }
    n_alive = 0;
    n_free  = 0;
    /* Put every pool slot back on the free list (descending, so LIFO pops
     * 0, 1, 2, ... in ascending order). */
    for (int i = pool_cap - 1; i >= 0; i--) {
        bug_pool[i].alive = 0;
        free_ids[n_free++] = i;
    }
    g_step = 0;
    g_births_last = g_deaths_last = 0;
    g_food_bug    = 0.0f;
    g_food_eaten_last = 0.0f;
    g_age_scale   = 50.0;
    act_reset();
    gact_reset();
}

void bugs_seed_with_density(float density)
{
    for (int y = 0; y < gN; y++) {
        for (int x = 0; x < gN; x++) {
            if (rng_uniform() < density) {
                int32_t bid = pool_alloc();
                bug_t  *b  = &bug_pool[bid];
                b->alive = 1;
                b->age   = 0;
                b->food  = g_initial_food;
                b->born_this_step = 0;
                genome_random(&b->genome);
                b->genome_hash = genome_hash_fn(&b->genome);
                /* Founder gets a fresh random color; all descendants
                 * inherit it unchanged (see reproduction path). */
                b->lineage_color = 0xFF000000u | (rng_u32() & 0x00FFFFFFu);
                for (int k = 0; k < EGENOME_N; k++)
                    b->egenome[k] = g_egenome_init[k];
                place_or_bump(bid, x, y);
                if (bug_pool[bid].alive) {
                    alive_ids[n_alive++] = bid;
                    g_food_bug += b->food;
                }
            }
        }
    }
}

/* ── Food diffusion (3×3 Moore mean, periodic) ─────────────────────── */

static void diffuse_once(void)
{
    int N = gN;
    for (int y = 0; y < N; y++) {
        for (int x = 0; x < N; x++) {
            float sum = 0.0f;
            for (int dy = -1; dy <= 1; dy++) {
                int yy = ((y + dy) % N + N) % N;
                for (int dx = -1; dx <= 1; dx++) {
                    int xx = ((x + dx) % N + N) % N;
                    sum += F_food[yy * N + xx];
                }
            }
            F_temp[y * N + x] = sum * (1.0f / 9.0f);
        }
    }
    float *tmp = F_food; F_food = F_temp; F_temp = tmp;
}

/* ── Neighborhood → 9-bit gene index (Moore) ───────────────────────── */

/* Per-bug: each of the 9 bits is thresholded by that bug's own egenome[p]
 * (bit p corresponds to Moore position p in reading order NW..SE). */
static inline int neighborhood_gene(const bug_t *b)
{
    int x = b->x, y = b->y;
    const float *e = b->egenome;
    int g = 0;
    if (F_food[gidx(x-1, y+1)] > e[0]) g |=   1;  /* NW  */
    if (F_food[gidx(x,   y+1)] > e[1]) g |=   2;  /* N   */
    if (F_food[gidx(x+1, y+1)] > e[2]) g |=   4;  /* NE  */
    if (F_food[gidx(x-1, y  )] > e[3]) g |=   8;  /* W   */
    if (F_food[gidx(x,   y  )] > e[4]) g |=  16;  /* C   */
    if (F_food[gidx(x+1, y  )] > e[5]) g |=  32;  /* E   */
    if (F_food[gidx(x-1, y-1)] > e[6]) g |=  64;  /* SW  */
    if (F_food[gidx(x,   y-1)] > e[7]) g |= 128;  /* S   */
    if (F_food[gidx(x+1, y-1)] > e[8]) g |= 256;  /* SE  */
    return g;
}

/* ── Fisher-Yates shuffle of alive_ids[] ───────────────────────────── */

static void shuffle_alive(void)
{
    for (int i = n_alive - 1; i > 0; i--) {
        int j = rng_int(i + 1);
        int32_t t = alive_ids[i]; alive_ids[i] = alive_ids[j]; alive_ids[j] = t;
    }
}

/* ── Activity hash table (ported from EvoCA) ───────────────────────── */

#define ACT_INIT_CAP 4096
#define ACT_EMPTY    0u

typedef struct {
    uint64_t activity;
    uint32_t pop_count;
    int32_t  color;
} act_entry_t;

static uint32_t    *act_keys = NULL;
static act_entry_t *act_vals = NULL;
static int          act_cap  = 0;
static int          act_cnt  = 0;
static int          act_ymax = 2000;

static void act_init_table(void)
{
    act_cap  = ACT_INIT_CAP;
    act_cnt  = 0;
    act_keys = calloc((size_t)act_cap, sizeof(uint32_t));
    act_vals = calloc((size_t)act_cap, sizeof(act_entry_t));
}

static void act_free_all(void)
{
    free(act_keys); act_keys = NULL;
    free(act_vals); act_vals = NULL;
    act_cap = act_cnt = 0;
}

static void act_reset(void)
{
    act_free_all();
    act_init_table();
}

static void act_resize(void)
{
    int new_cap = act_cap * 2;
    uint32_t    *nk = calloc((size_t)new_cap, sizeof(uint32_t));
    act_entry_t *nv = calloc((size_t)new_cap, sizeof(act_entry_t));
    for (int i = 0; i < act_cap; i++) {
        if (act_keys[i] == ACT_EMPTY) continue;
        uint32_t slot = act_keys[i] % (uint32_t)new_cap;
        while (nk[slot] != ACT_EMPTY)
            slot = (slot + 1) % (uint32_t)new_cap;
        nk[slot] = act_keys[i];
        nv[slot] = act_vals[i];
    }
    free(act_keys); free(act_vals);
    act_keys = nk; act_vals = nv; act_cap = new_cap;
}

static act_entry_t *act_find_or_insert(uint32_t key, int32_t color)
{
    if (act_cnt * 10 >= act_cap * 7) act_resize();
    uint32_t slot = key % (uint32_t)act_cap;
    while (act_keys[slot] != ACT_EMPTY) {
        if (act_keys[slot] == key) return &act_vals[slot];
        slot = (slot + 1) % (uint32_t)act_cap;
    }
    act_keys[slot] = key;
    act_vals[slot].activity  = 0;
    act_vals[slot].pop_count = 0;
    act_vals[slot].color     = color;
    act_cnt++;
    return &act_vals[slot];
}

static void act_compact(uint64_t threshold)
{
    int keep = 0;
    for (int i = 0; i < act_cap; i++) {
        if (act_keys[i] == ACT_EMPTY) continue;
        if (act_vals[i].pop_count > 0 || act_vals[i].activity >= threshold)
            keep++;
    }
    int new_cap = ACT_INIT_CAP;
    while (new_cap * 7 < keep * 10 + 10) new_cap *= 2;

    uint32_t    *nk = calloc((size_t)new_cap, sizeof(uint32_t));
    act_entry_t *nv = calloc((size_t)new_cap, sizeof(act_entry_t));
    int new_cnt = 0;
    for (int i = 0; i < act_cap; i++) {
        if (act_keys[i] == ACT_EMPTY) continue;
        if (act_vals[i].pop_count == 0 && act_vals[i].activity < threshold)
            continue;
        uint32_t slot = act_keys[i] % (uint32_t)new_cap;
        while (nk[slot] != ACT_EMPTY) slot = (slot + 1) % (uint32_t)new_cap;
        nk[slot] = act_keys[i];
        nv[slot] = act_vals[i];
        new_cnt++;
    }
    free(act_keys); free(act_vals);
    act_keys = nk; act_vals = nv;
    act_cap  = new_cap;
    act_cnt  = new_cnt;
}

void bugs_set_act_ymax(int y) { if (y > 0) act_ymax = y; }
int  bugs_get_act_ymax(void)  { return act_ymax; }

void bugs_activity_update(void)
{
    if (!act_keys) return;
    for (int i = 0; i < act_cap; i++)
        if (act_keys[i] != ACT_EMPTY)
            act_vals[i].pop_count = 0;

    for (int i = 0; i < n_alive; i++) {
        bug_t *b = &bug_pool[alive_ids[i]];
        act_entry_t *e = act_find_or_insert(b->genome_hash,
                                            hash_to_color(b->genome_hash));
        e->pop_count++;
        e->activity++;
    }

    if (act_cnt > 50000)
        act_compact((uint64_t)act_ymax / 10);
}

void bugs_activity_render_col(int32_t *col, int height)
{
    for (int y = 0; y < height; y++)
        col[y] = (int32_t)0xFF111111u;

    if (!act_keys || act_cnt == 0) return;

    uint64_t ymax = (uint64_t)act_ymax;
    /* Per-y-row winner: stable lexicographic priority (pop, activity, key)
     * descending. Pop-first keeps live buckets above extinct at the same row;
     * activity and key are tie-breakers that don't depend on hash-table slot
     * order, so the rendered profile stays consistent across act_resize()
     * events that reshuffle iteration order. */
    uint32_t ypop[height];
    uint64_t yact[height];
    uint32_t ykey[height];
    uint32_t ycol[height];
    for (int y = 0; y < height; y++) {
        ypop[y] = 0; yact[y] = 0; ykey[y] = 0; ycol[y] = 0;
    }

    for (int i = 0; i < act_cap; i++) {
        uint32_t key = act_keys[i];
        if (key == ACT_EMPTY) continue;
        uint32_t pop = act_vals[i].pop_count;
        uint64_t act = act_vals[i].activity;
        int y = (height - 1) - (int)((uint64_t)(height - 1) * act / (act + ymax));
        if (y < 0) y = 0;
        if (y >= height) y = height - 1;
        int better =
            pop >  ypop[y] ||
            (pop == ypop[y] && act >  yact[y]) ||
            (pop == ypop[y] && act == yact[y] && key > ykey[y]);
        if (better) {
            ypop[y] = pop;
            yact[y] = act;
            ykey[y] = key;
            ycol[y] = (uint32_t)act_vals[i].color;
        }
    }

    for (int y = 0; y < height; y++) {
        if (ykey[y] == 0) continue;      /* no bucket mapped to this row */
        uint32_t c = ycol[y];
        if (ypop[y] == 0) {
            /* extinct bucket — dimmed to 15% */
            uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 15 / 100);
            uint8_t g = (uint8_t)(((c >>  8) & 0xFF) * 15 / 100);
            uint8_t b = (uint8_t)(( c        & 0xFF) * 15 / 100);
            col[y] = (int32_t)(0xFF000000u | ((uint32_t)r << 16)
                              | ((uint32_t)g << 8) | b);
        } else {
            col[y] = (int32_t)c;
        }
    }
}

int bugs_activity_get(uint32_t *keys, uint64_t *activities,
                      uint32_t *pop_counts, int32_t *colors, int max_n)
{
    int n = 0;
    if (!act_keys) return 0;
    for (int i = 0; i < act_cap && n < max_n; i++) {
        if (act_keys[i] == ACT_EMPTY) continue;
        keys[n]       = act_keys[i];
        activities[n] = act_vals[i].activity;
        pop_counts[n] = act_vals[i].pop_count;
        colors[n]     = act_vals[i].color;
        n++;
    }
    return n;
}

/* ── q_activity: deciles of normalized cumulative activity ─────────── */

static int _float_cmp(const void *a, const void *b)
{
    float fa = *(const float *)a, fb = *(const float *)b;
    return (fa > fb) - (fa < fb);
}

void bugs_q_activity_deciles(float *deciles_out)
{
    if (!act_keys || act_cnt == 0) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    int D = 0;
    for (int i = 0; i < act_cap; i++)
        if (act_keys[i] != ACT_EMPTY && act_vals[i].pop_count > 0)
            D++;
    if (D == 0) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    float *buf = (float *)malloc((size_t)D * sizeof(float));
    if (!buf) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    int n = 0;
    float inv_D = 1.0f / (float)D;
    for (int i = 0; i < act_cap; i++) {
        if (act_keys[i] == ACT_EMPTY || act_vals[i].pop_count == 0) continue;
        buf[n++] = (float)act_vals[i].activity * inv_D;
    }
    qsort(buf, (size_t)n, sizeof(float), _float_cmp);
    for (int d = 0; d < 9; d++) {
        int idx = (int)((float)(d + 1) * 0.1f * (float)n);
        if (idx >= n) idx = n - 1;
        deciles_out[d] = buf[idx];
    }
    free(buf);
}

/* ── g-activity: per-(input, output) pair ──────────────────────────────
 *
 * Distinct from the "activity" table above (which is renamed G-activity at
 * the API level): there the key is a hash of the WHOLE genome. Here the key
 * encodes a single (neighborhood pattern, move) pair — the input/output of
 * one LUT slot. Each live bug contributes one sample per update, for the
 * LUT entry it is currently "using" (the gene indexed by its current 9-bit
 * Moore neighborhood).
 *
 * Key layout (32-bit, high bit set so it is never the ACT_EMPTY sentinel 0):
 *   bit 31      : always 1
 *   bits 30..16 : nbhd (0..511, takes bits 24..16)
 *   bits 15.. 8 : dx + 15 (0..30)
 *   bits  7.. 0 : dy + 15 (0..30)
 */

static uint32_t    *gact_keys = NULL;
static act_entry_t *gact_vals = NULL;
static int          gact_cap  = 0;
static int          gact_cnt  = 0;
static int          gact_ymax = 2000;

static void gact_init_table(void)
{
    gact_cap  = ACT_INIT_CAP;
    gact_cnt  = 0;
    gact_keys = calloc((size_t)gact_cap, sizeof(uint32_t));
    gact_vals = calloc((size_t)gact_cap, sizeof(act_entry_t));
}

static void gact_free_all(void)
{
    free(gact_keys); gact_keys = NULL;
    free(gact_vals); gact_vals = NULL;
    gact_cap = gact_cnt = 0;
}

static void gact_reset(void)
{
    gact_free_all();
    gact_init_table();
}

static void gact_resize(void)
{
    int new_cap = gact_cap * 2;
    uint32_t    *nk = calloc((size_t)new_cap, sizeof(uint32_t));
    act_entry_t *nv = calloc((size_t)new_cap, sizeof(act_entry_t));
    for (int i = 0; i < gact_cap; i++) {
        if (gact_keys[i] == ACT_EMPTY) continue;
        uint32_t slot = gact_keys[i] % (uint32_t)new_cap;
        while (nk[slot] != ACT_EMPTY)
            slot = (slot + 1) % (uint32_t)new_cap;
        nk[slot] = gact_keys[i];
        nv[slot] = gact_vals[i];
    }
    free(gact_keys); free(gact_vals);
    gact_keys = nk; gact_vals = nv; gact_cap = new_cap;
}

static act_entry_t *gact_find_or_insert(uint32_t key, int32_t color)
{
    if (gact_cnt * 10 >= gact_cap * 7) gact_resize();
    uint32_t slot = key % (uint32_t)gact_cap;
    while (gact_keys[slot] != ACT_EMPTY) {
        if (gact_keys[slot] == key) return &gact_vals[slot];
        slot = (slot + 1) % (uint32_t)gact_cap;
    }
    gact_keys[slot] = key;
    gact_vals[slot].activity  = 0;
    gact_vals[slot].pop_count = 0;
    gact_vals[slot].color     = color;
    gact_cnt++;
    return &gact_vals[slot];
}

static void gact_compact(uint64_t threshold)
{
    int keep = 0;
    for (int i = 0; i < gact_cap; i++) {
        if (gact_keys[i] == ACT_EMPTY) continue;
        if (gact_vals[i].pop_count > 0 || gact_vals[i].activity >= threshold)
            keep++;
    }
    int new_cap = ACT_INIT_CAP;
    while (new_cap * 7 < keep * 10 + 10) new_cap *= 2;

    uint32_t    *nk = calloc((size_t)new_cap, sizeof(uint32_t));
    act_entry_t *nv = calloc((size_t)new_cap, sizeof(act_entry_t));
    int new_cnt = 0;
    for (int i = 0; i < gact_cap; i++) {
        if (gact_keys[i] == ACT_EMPTY) continue;
        if (gact_vals[i].pop_count == 0 && gact_vals[i].activity < threshold)
            continue;
        uint32_t slot = gact_keys[i] % (uint32_t)new_cap;
        while (nk[slot] != ACT_EMPTY) slot = (slot + 1) % (uint32_t)new_cap;
        nk[slot] = gact_keys[i];
        nv[slot] = gact_vals[i];
        new_cnt++;
    }
    free(gact_keys); free(gact_vals);
    gact_keys = nk; gact_vals = nv;
    gact_cap  = new_cap;
    gact_cnt  = new_cnt;
}

void bugs_set_g_act_ymax(int y) { if (y > 0) gact_ymax = y; }
int  bugs_get_g_act_ymax(void)  { return gact_ymax; }

static inline uint32_t g_pair_key(int nbhd, int8_t dx, int8_t dy)
{
    return 0x80000000u
         | ((uint32_t)(nbhd & 0x1FF) << 16)
         | ((uint32_t)(uint8_t)(dx + 15) << 8)
         |  (uint32_t)(uint8_t)(dy + 15);
}

void bugs_g_activity_update(void)
{
    if (!gact_keys) return;
    for (int i = 0; i < gact_cap; i++)
        if (gact_keys[i] != ACT_EMPTY)
            gact_vals[i].pop_count = 0;

    for (int i = 0; i < n_alive; i++) {
        bug_t *b = &bug_pool[alive_ids[i]];
        int nbhd = neighborhood_gene(b);
        gene_t  g = b->genome.genes[nbhd];
        uint32_t key = g_pair_key(nbhd, g.dx, g.dy);
        act_entry_t *e = gact_find_or_insert(key, hash_to_color(mix32(key)));
        e->pop_count++;
        e->activity++;
    }

    if (gact_cnt > 200000)
        gact_compact((uint64_t)gact_ymax / 10);
}

void bugs_g_activity_render_col(int32_t *col, int height)
{
    for (int y = 0; y < height; y++)
        col[y] = (int32_t)0xFF111111u;

    if (!gact_keys || gact_cnt == 0) return;

    uint64_t ymax = (uint64_t)gact_ymax;
    /* Stable (pop, activity, key) lexicographic priority — see
     * bugs_activity_render_col for rationale. */
    uint32_t ypop[height];
    uint64_t yact[height];
    uint32_t ykey[height];
    uint32_t ycol[height];
    for (int y = 0; y < height; y++) {
        ypop[y] = 0; yact[y] = 0; ykey[y] = 0; ycol[y] = 0;
    }

    for (int i = 0; i < gact_cap; i++) {
        uint32_t key = gact_keys[i];
        if (key == ACT_EMPTY) continue;
        uint32_t pop = gact_vals[i].pop_count;
        uint64_t act = gact_vals[i].activity;
        int y = (height - 1) - (int)((uint64_t)(height - 1) * act / (act + ymax));
        if (y < 0) y = 0;
        if (y >= height) y = height - 1;
        int better =
            pop >  ypop[y] ||
            (pop == ypop[y] && act >  yact[y]) ||
            (pop == ypop[y] && act == yact[y] && key > ykey[y]);
        if (better) {
            ypop[y] = pop;
            yact[y] = act;
            ykey[y] = key;
            ycol[y] = (uint32_t)gact_vals[i].color;
        }
    }

    for (int y = 0; y < height; y++) {
        if (ykey[y] == 0) continue;
        uint32_t c = ycol[y];
        if (ypop[y] == 0) {
            uint8_t r = (uint8_t)(((c >> 16) & 0xFF) * 15 / 100);
            uint8_t g = (uint8_t)(((c >>  8) & 0xFF) * 15 / 100);
            uint8_t b = (uint8_t)(( c        & 0xFF) * 15 / 100);
            col[y] = (int32_t)(0xFF000000u | ((uint32_t)r << 16)
                              | ((uint32_t)g << 8) | b);
        } else {
            col[y] = (int32_t)c;
        }
    }
}

int bugs_g_activity_get(uint32_t *keys, uint64_t *activities,
                        uint32_t *pop_counts, int32_t *colors, int max_n)
{
    int n = 0;
    if (!gact_keys) return 0;
    for (int i = 0; i < gact_cap && n < max_n; i++) {
        if (gact_keys[i] == ACT_EMPTY) continue;
        keys[n]       = gact_keys[i];
        activities[n] = gact_vals[i].activity;
        pop_counts[n] = gact_vals[i].pop_count;
        colors[n]     = gact_vals[i].color;
        n++;
    }
    return n;
}

void bugs_gq_activity_deciles(float *deciles_out)
{
    if (!gact_keys || gact_cnt == 0) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    int D = 0;
    for (int i = 0; i < gact_cap; i++)
        if (gact_keys[i] != ACT_EMPTY && gact_vals[i].pop_count > 0)
            D++;
    if (D == 0) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    float *buf = (float *)malloc((size_t)D * sizeof(float));
    if (!buf) {
        for (int i = 0; i < 9; i++) deciles_out[i] = 0.0f;
        return;
    }
    int n = 0;
    float inv_D = 1.0f / (float)D;
    for (int i = 0; i < gact_cap; i++) {
        if (gact_keys[i] == ACT_EMPTY || gact_vals[i].pop_count == 0) continue;
        buf[n++] = (float)gact_vals[i].activity * inv_D;
    }
    qsort(buf, (size_t)n, sizeof(float), _float_cmp);
    for (int d = 0; d < 9; d++) {
        int idx = (int)((float)(d + 1) * 0.1f * (float)n);
        if (idx >= n) idx = n - 1;
        deciles_out[d] = buf[idx];
    }
    free(buf);
}

/* ── Bug-coloring: per-LUT-index move histogram ───────────────────── */

void bugs_bug_coloring_hist(int gene_idx, int32_t *hist_out)
{
    memset(hist_out, 0, 31 * 31 * sizeof(int32_t));
    if (gene_idx < 0 || gene_idx >= N_GENES) return;
    for (int i = 0; i < n_alive; i++) {
        bug_t *b = &bug_pool[alive_ids[i]];
        gene_t mv = b->genome.genes[gene_idx];
        int bx = (int)mv.dx + 15;
        int by = (int)mv.dy + 15;
        if (bx < 0 || bx > 30 || by < 0 || by > 30) continue;
        hist_out[by * 31 + bx]++;
    }
}

/* ── Time step ─────────────────────────────────────────────────────── */

void bugs_step(void)
{
    size_t cells = (size_t)gN * gN;

    /* Phase 1: food regeneration toward source */
    if (g_food_inc > 0.0f) {
        for (size_t i = 0; i < cells; i++) {
            float v = F_food[i] + g_food_inc;
            if (v > F_src[i]) v = F_src[i];
            F_food[i] = v;
        }
    }

    /* Phase 2: diffusion */
    for (int d = 0; d < g_gdiff; d++) diffuse_once();

    /* Phase 3: bug updates in random order */
    shuffle_alive();

    g_births_last = 0;
    g_deaths_last = 0;
    g_food_eaten_last = 0.0f;

    int n_before = n_alive;
    int new_alive_count = 0;

    for (int i = 0; i < n_before; i++) {
        int32_t bid = alive_ids[i];
        bug_t *b = &bug_pool[bid];
        if (!b->alive) continue;   /* (shouldn't happen) */

        /* Death check */
        if (b->food <= 0.0f) {
            bug_at[gidx(b->x, b->y)] = -1;
            bug_mask[gidx(b->x, b->y)] = 0;
            g_food_bug -= b->food;       /* subtract current value (may be 0) */
            pool_release(bid);
            g_deaths_last++;
            continue;
        }

        /* Reproduction check */
        if (b->food > g_reproduction_food) {
            float half = b->food * 0.5f;
            b->food = half;

            int32_t cid = pool_alloc();
            bug_t *c = &bug_pool[cid];
            c->alive = 1;
            c->age   = 0;
            c->food  = half;
            c->born_this_step = 1;
            genome_mutate_copy(&b->genome, &c->genome, g_mutation_rate);
            egenome_mutate_copy(b->egenome, c->egenome, g_mu_egenome);
            c->genome_hash = genome_hash_fn(&c->genome);
            c->lineage_color = b->lineage_color;   /* inherit unchanged */
            place_or_bump(cid, b->x, b->y);
            if (bug_pool[cid].alive) {
                alive_ids[n_before + new_alive_count++] = cid;
                g_food_bug += c->food;
                g_births_last++;
            } else {
                /* place_or_bump already released the slot */
                g_food_bug -= half;      /* parent's half still counted below */
                b->food = half * 2.0f;   /* undo split if child never placed */
                g_food_bug += half;
            }
        }

        /* Eat from current cell (food field is float, consumed) */
        int here = gidx(b->x, b->y);
        float here_food = F_food[here];
        float eat = g_eat_amount < here_food ? g_eat_amount : here_food;
        if (eat > 0.0f) {
            F_food[here]  -= eat;
            b->food       += eat;
            g_food_bug    += eat;
            g_food_eaten_last += eat;
        }

        /* Tax: always applied */
        b->food    -= g_movement_cost;
        g_food_bug -= g_movement_cost;

        b->age++;

        /* Look up move */
        int gi = neighborhood_gene(b);
        gene_t mv = b->genome.genes[gi];

        /* Move bug */
        bug_at[here] = -1;
        bug_mask[here] = 0;
        place_or_bump(bid, b->x + mv.dx, b->y + mv.dy);
    }

    /* Rebuild alive_ids from scratch (compact out the dead) */
    int k = 0;
    for (int i = 0; i < n_before + new_alive_count; i++) {
        int32_t bid = alive_ids[i];
        if (bid >= 0 && bug_pool[bid].alive) alive_ids[k++] = bid;
    }
    n_alive = k;

    /* clear born-this-step flags */
    for (int i = 0; i < n_alive; i++)
        bug_pool[alive_ids[i]].born_this_step = 0;

    g_step++;
}

/* ── Accessors ─────────────────────────────────────────────────────── */

int      bugs_get_N(void)          { return gN; }
int      bugs_get_cell_px(void)    { return CELL_PX; }
uint32_t bugs_get_step(void)       { return g_step; }
int      bugs_get_population(void) { return n_alive; }
int      bugs_get_births_last(void){ return g_births_last; }
int      bugs_get_deaths_last(void){ return g_deaths_last; }
float    bugs_get_food_bug(void)   { return g_food_bug; }
float    bugs_get_food_env(void)
{
    double s = 0.0;
    size_t cells = (size_t)gN * gN;
    for (size_t i = 0; i < cells; i++) s += F_food[i];
    return (float)s;
}
float    bugs_get_food_eaten_last(void) { return g_food_eaten_last; }
float   *bugs_get_food_field(void)  { return F_food; }
float   *bugs_get_food_source(void) { return F_src; }
uint8_t *bugs_get_bug_mask(void)    { return bug_mask; }

/* Diversity counters ─────────────────────────────────────────────── */

static int _u32_cmp(const void *a, const void *b)
{
    uint32_t ua = *(const uint32_t *)a, ub = *(const uint32_t *)b;
    return (ua > ub) - (ua < ub);
}

/* Number of distinct genome_hash values across alive bugs. */
int bugs_count_distinct_genomes(void)
{
    if (n_alive <= 0) return 0;
    uint32_t *buf = (uint32_t *)malloc((size_t)n_alive * sizeof(uint32_t));
    if (!buf) return 0;
    for (int i = 0; i < n_alive; i++)
        buf[i] = bug_pool[alive_ids[i]].genome_hash;
    qsort(buf, (size_t)n_alive, sizeof(uint32_t), _u32_cmp);
    int distinct = 1;
    for (int i = 1; i < n_alive; i++)
        if (buf[i] != buf[i - 1]) distinct++;
    free(buf);
    return distinct;
}

/* Number of distinct (nbhd, dx, dy) input/output pairs across alive bugs,
 * using each bug's *current* neighborhood pattern as the input. Shares
 * the g_pair_key packing scheme with the g-activity probe, so the key
 * space is the same. */
int bugs_count_distinct_io_pairs(void)
{
    if (n_alive <= 0) return 0;
    uint32_t *buf = (uint32_t *)malloc((size_t)n_alive * sizeof(uint32_t));
    if (!buf) return 0;
    for (int i = 0; i < n_alive; i++) {
        bug_t *b = &bug_pool[alive_ids[i]];
        int nbhd = neighborhood_gene(b);
        gene_t g = b->genome.genes[nbhd];
        buf[i] = g_pair_key(nbhd, g.dx, g.dy);
    }
    qsort(buf, (size_t)n_alive, sizeof(uint32_t), _u32_cmp);
    int distinct = 1;
    for (int i = 1; i < n_alive; i++)
        if (buf[i] != buf[i - 1]) distinct++;
    free(buf);
    return distinct;
}

/* Population mean and std-dev of each egenome entry (9 positions).
 * mean_out[9] and std_out[9] are overwritten; both filled with zeros
 * when the population is empty. Either pointer may be NULL. */
void bugs_egenome_stats(float *mean_out, float *std_out)
{
    float mean[EGENOME_N];
    float var [EGENOME_N];
    for (int p = 0; p < EGENOME_N; p++) { mean[p] = 0.0f; var[p] = 0.0f; }

    if (n_alive > 0) {
        double sum[EGENOME_N] = {0};
        double sqr[EGENOME_N] = {0};
        for (int i = 0; i < n_alive; i++) {
            const float *e = bug_pool[alive_ids[i]].egenome;
            for (int p = 0; p < EGENOME_N; p++) {
                sum[p] += e[p];
                sqr[p] += (double)e[p] * (double)e[p];
            }
        }
        double inv = 1.0 / (double)n_alive;
        for (int p = 0; p < EGENOME_N; p++) {
            double m = sum[p] * inv;
            double v = sqr[p] * inv - m * m;
            if (v < 0.0) v = 0.0;
            mean[p] = (float)m;
            var[p]  = (float)v;
        }
    }
    if (mean_out) for (int p = 0; p < EGENOME_N; p++) mean_out[p] = mean[p];
    if (std_out)  for (int p = 0; p < EGENOME_N; p++) std_out[p]  = sqrtf(var[p]);
}

/* Copy all alive bugs' egenomes into out as a contiguous (pop, EGENOME_N)
 * array. out must hold at least max_pop*EGENOME_N floats. Returns the
 * number of rows written (min(n_alive, max_pop)). */
int bugs_get_egenome_all(float *out, int max_pop)
{
    if (!out || max_pop <= 0) return 0;
    int n = n_alive < max_pop ? n_alive : max_pop;
    for (int i = 0; i < n; i++) {
        const float *e = bug_pool[alive_ids[i]].egenome;
        for (int p = 0; p < EGENOME_N; p++) {
            out[(size_t)i * EGENOME_N + p] = e[p];
        }
    }
    return n;
}

int bugs_get_ages(int32_t *out, int max_pop)
{
    if (!out || max_pop <= 0) return 0;
    int n = n_alive < max_pop ? n_alive : max_pop;
    for (int i = 0; i < n; i++) {
        out[i] = bug_pool[alive_ids[i]].age;
    }
    return n;
}

/* ── Colorize ──────────────────────────────────────────────────────── */

static inline int32_t mk_argb(uint8_t r, uint8_t g, uint8_t b)
{
    return (int32_t)(0xFF000000u | ((uint32_t)r << 16)
                    | ((uint32_t)g << 8) | b);
}

void bugs_colorize(int32_t *pixels, int colormode)
{
    size_t cells = (size_t)gN * gN;
    /* Background: food field as green */
    for (size_t i = 0; i < cells; i++) {
        float f = F_food[i];
        if (f < 0.0f) f = 0.0f;
        if (f > 1.0f) f = 1.0f;
        uint8_t g = (uint8_t)(f * 200.0f + 20.0f * (f > 0.0f));
        pixels[i] = mk_argb(0, g, 0);
    }

    /* Bug-age autoscale: pre-scan alive bugs once. Fast up (jump to any
     * new observed max), slow down (geometric decay) so quiet periods let
     * the scale relax back. Floor prevents divide-by-zero blowups. */
    if (colormode == 3) {
        int max_age = 0;
        for (int i = 0; i < n_alive; i++) {
            int a = bug_pool[alive_ids[i]].age;
            if (a > max_age) max_age = a;
        }
        if ((double)max_age > g_age_scale) g_age_scale = (double)max_age;
        else                                g_age_scale *= 0.995;
        if (g_age_scale < 10.0) g_age_scale = 10.0;
    }

    /* Overlay bugs */
    for (int i = 0; i < n_alive; i++) {
        int32_t bid = alive_ids[i];
        bug_t *b = &bug_pool[bid];
        int idx = gidx(b->x, b->y);
        int32_t c;
        if (colormode == 1) {
            c = hash_to_color(b->genome_hash);
        } else if (colormode == 2) {
            float f = b->food / (g_reproduction_food > 0.0f
                                 ? g_reproduction_food : 1.0f);
            if (f < 0.0f) f = 0.0f;
            if (f > 1.0f) f = 1.0f;
            uint8_t v = (uint8_t)(f * 255.0f);
            c = mk_argb(v, v, v);
        } else if (colormode == 3) {
            /* bug-age: age/g_age_scale mapped to cool→hot gradient. */
            float v = (float)((double)b->age / g_age_scale);
            if (v < 0.0f) v = 0.0f;
            if (v > 1.0f) v = 1.0f;
            uint8_t R = (uint8_t)(80.0f  + 175.0f * v);
            uint8_t G = (uint8_t)(60.0f  + 560.0f * v * (1.0f - v));
            uint8_t B = (uint8_t)(40.0f  + 180.0f * (1.0f - v));
            c = mk_argb(R, G, B);
        } else if (colormode == 4) {
            /* lineage: random color at seed, inherited unchanged on birth. */
            c = (int32_t)b->lineage_color;
        } else {
            /* default: red dot */
            c = mk_argb(255, 60, 60);
        }
        pixels[idx] = c;
    }
}
