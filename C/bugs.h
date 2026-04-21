#ifndef BUGS_H
#define BUGS_H

#include <stdint.h>

/*
 * Bugs — port of CocoaBugs' "Packard Bugs" model to C.
 *
 * Agents live on an N×N periodic grid with a float food field F(x) ∈ [0, 1].
 * Each bug carries a lookup table of 32 movement genes indexed by a 5-bit
 * neighborhood pattern:
 *
 *     bit 0 : F(x, y+1) > food_threshold      (up)
 *     bit 1 : F(x-1, y) > food_threshold      (left)
 *     bit 2 : F(x,   y) > food_threshold      (self)
 *     bit 3 : F(x+1, y) > food_threshold      (right)
 *     bit 4 : F(x, y-1) > food_threshold      (down)
 *
 * Each gene encodes one of 120 moves: 8 directions × 15 magnitudes (1..15).
 * Stored as (int8_t dx, int8_t dy, uint8_t mag, uint8_t dir) per slot.
 *
 * Display scale: screen pixels per simulation cell.  Change and recompile.
 */
#define CELL_PX  4

#define N_GENES       32
#define MAG_MAX       15
#define N_DIRS         8

/* ── Lifecycle ─────────────────────────────────────────────────────── */

void bugs_init(int N);
void bugs_free(void);
void bugs_set_seed(uint64_t s);

/* ── Metaparam setters ─────────────────────────────────────────────── */

void bugs_set_mutation_rate(float r);        /* per gene slot, per birth */
void bugs_set_reproduction_food(float t);    /* bug reproduces when food > t */
void bugs_set_movement_cost(float c);        /* ≥0: food lost per tick */
void bugs_set_eat_amount(float a);           /* ≥0: max food eaten per tick */
void bugs_set_initial_food(float f);         /* initial bug food */
void bugs_set_food_inc(float i);             /* F(x) regenerates toward source */
void bugs_set_food_threshold(float t);       /* F(x) > t → gene bit = 1 */
void bugs_set_gdiff(int d);                  /* diffusion passes per tick */

float bugs_get_mutation_rate(void);
float bugs_get_reproduction_food(void);
float bugs_get_movement_cost(void);
float bugs_get_eat_amount(void);
float bugs_get_initial_food(void);
float bugs_get_food_inc(void);
float bugs_get_food_threshold(void);
int   bugs_get_gdiff(void);

/* ── Food field setup ──────────────────────────────────────────────── */

/* Set the regeneration target field F_source(x) directly (float [0,1]).
 * Length must be N*N. Also copies into the live food field F(x). */
void bugs_set_food_source(const float *src);

/* Set F_source from an image: src is brightness in [0,1], len N*N.
 * Pixels with brightness < threshold become food_source=1, else 0. */
void bugs_set_food_source_from_brightness(const float *brightness, float thresh);

/* ── Seeding ───────────────────────────────────────────────────────── */

void bugs_exterminate(void);            /* kill all bugs */
void bugs_seed_with_density(float d);   /* place a bug on each cell w/ prob d */

/* ── Step ──────────────────────────────────────────────────────────── */

void bugs_step(void);

/* ── Accessors ─────────────────────────────────────────────────────── */

int      bugs_get_N(void);
int      bugs_get_cell_px(void);
uint32_t bugs_get_step(void);
int      bugs_get_population(void);     /* alive bug count */
int      bugs_get_births_last(void);    /* births on last step */
int      bugs_get_deaths_last(void);    /* deaths on last step */
float    bugs_get_food_bug(void);       /* Σ food over alive bugs */
float    bugs_get_food_env(void);       /* Σ F(x) over grid */
float   *bugs_get_food_field(void);     /* [N*N] live F(x) */
float   *bugs_get_food_source(void);    /* [N*N] regen target */
uint8_t *bugs_get_bug_mask(void);       /* [N*N] 1 if a bug is on that cell */

/* ── Colorize ──────────────────────────────────────────────────────── */

/* Fill pixels[N*N] with ARGB int32.
 * colormode 0 : food field green + bugs red
 * colormode 1 : food field green + bugs hash-colored by genome
 * colormode 2 : food field green + bugs brightness-by-food
 */
void bugs_colorize(int32_t *pixels, int colormode);

/* ── Activity probe (per-genome) ───────────────────────────────────── */

void bugs_activity_update(void);
void bugs_activity_render_col(int32_t *col, int height);
int  bugs_activity_get(uint32_t *keys, uint64_t *activities,
                       uint32_t *pop_counts, int32_t *colors, int max_n);
void bugs_set_act_ymax(int y);
int  bugs_get_act_ymax(void);

/* ── Activity quantile probe (9 deciles p10..p90) ──────────────────── */

void bugs_q_activity_deciles(float *deciles_out);

#endif /* BUGS_H */
