// SPDX-License-Identifier: GPL-3.0-or-later
// Marcin Kowalik <mkowalik@agh.edu.pl> | m300_oled_idle.h - Zapisuje parę DIM i SLEEP w dwustronicowym dzienniku Flash i odczytuje ostatni kompletny wpis.
#ifndef M300_OLED_IDLE_H
#define M300_OLED_IDLE_H
#include <stdint.h>

#define OLED_PAGE_BYTES 2048u
#define OLED_SLOT_WORDS 8u
#define OLED_SLOTS (2u * OLED_PAGE_BYTES / (2u * OLED_SLOT_WORDS))
#define OLED_TAG 0xb54du

struct oled_io {
    void *ctx;
    uint16_t (*read)(void *, unsigned);
    int (*write)(void *, unsigned, uint16_t);
    int (*erase)(void *, unsigned);
};

struct oled_entry {
    unsigned slot;
    uint32_t generation;
    uint16_t pair;
    int valid;
};

static inline int
oled_pair_valid(uint16_t pair)
{
    unsigned dim = pair >> 8, sleep = pair & 255;
    return dim >= 1 && dim <= sleep && sleep <= 60;
}

// Both individual choices are stored. Runtime dimming never follows sleep.
static inline int
oled_pref_valid(uint16_t pair)
{
    unsigned preferred = pair >> 8, sleep = pair & 255;
    return preferred >= 1 && preferred <= 60 && sleep >= 1 && sleep <= 60;
}

static inline uint16_t
oled_effective(uint16_t pair)
{
    unsigned sleep = pair & 255;
    return (pair >> 8) > sleep ? (sleep << 8) | sleep : pair;
}

static inline uint16_t
oled_record_kind(uint16_t pair)
{
    return oled_pair_valid(pair) ? 0x4f4c : 0x4f50;
}

static inline struct oled_entry
oled_latest(const struct oled_io *io)
{
    struct oled_entry best = {0};
    for (unsigned s = 0; s < OLED_SLOTS; s++) {
        unsigned i = s * OLED_SLOT_WORDS;
        if (io->read(io->ctx, i + 7) != OLED_TAG)
            continue;
        uint16_t lo = io->read(io->ctx, i), hi = io->read(io->ctx, i+1);
        uint16_t pair = io->read(io->ctx, i+2);
        if ((lo ^ io->read(io->ctx, i+3)) != UINT16_MAX
            || (hi ^ io->read(io->ctx, i+4)) != UINT16_MAX
            || (pair ^ io->read(io->ctx, i+5)) != UINT16_MAX
            || !oled_pref_valid(pair) || io->read(io->ctx, i+6) != oled_record_kind(pair))
            continue;
        uint32_t gen = lo | ((uint32_t)hi << 16);
        if (!best.valid || (int32_t)(gen - best.generation) > 0)
            best = (struct oled_entry){s, gen, pair, 1};
    }
    return best;
}

static inline int
oled_blank(const struct oled_io *io, unsigned slot)
{
    for (unsigned j = 0; j < OLED_SLOT_WORDS; j++)
        if (io->read(io->ctx, slot * OLED_SLOT_WORDS+j) != UINT16_MAX)
            return 0;
    return 1;
}

// Program the commit marker last. Never erase the page holding the latest
// valid entry. Torn slots are skipped. Same-value requests consume no flash.
static inline int
oled_store(const struct oled_io *io, struct oled_entry best, uint16_t pair)
{
    if (!oled_pref_valid(pair))
        return 0;
    if (best.valid && pair == best.pair)
        return 1;
    unsigned per_page = OLED_SLOTS / 2, slot = best.valid ? best.slot+1 : 0;
    unsigned end = best.valid && best.slot >= per_page ? OLED_SLOTS : per_page;
    while (slot < end && !oled_blank(io, slot))
        slot++;
    if (slot == end) {
        slot = end == per_page ? per_page : 0;
        if (!oled_blank(io, slot) && !io->erase(io->ctx, slot * OLED_SLOT_WORDS))
            return 0;
    }
    uint32_t gen = best.generation+1;
    uint16_t lo = gen, hi = gen >> 16;
    const uint16_t record[] = {lo,hi,pair,(uint16_t)~lo,(uint16_t)~hi,
                               (uint16_t)~pair,oled_record_kind(pair),OLED_TAG};
    for (unsigned j = 0; j < OLED_SLOT_WORDS; j++) {
        unsigned pos = slot * OLED_SLOT_WORDS+j;
        if ((record[j] != UINT16_MAX && !io->write(io->ctx,pos,record[j]))
            || io->read(io->ctx,pos) != record[j])
            return 0;
    }
    return 1;
}
#endif
