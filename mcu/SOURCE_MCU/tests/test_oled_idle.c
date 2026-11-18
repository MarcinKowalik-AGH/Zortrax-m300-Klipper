// SPDX-License-Identifier: GPL-3.0-or-later
// Marcin Kowalik <mkowalik@agh.edu.pl>
#include <assert.h>
#include <string.h>
#include "../overlay/src/stm32/m300_oled_idle.h"

struct flash { uint16_t words[OLED_PAGE_BYTES]; int budget, written, erased; };
static uint16_t read_word(void *ctx, unsigned i) {
    assert(i < OLED_PAGE_BYTES);
    return ((struct flash *)ctx)->words[i];
}
static int program(void *ctx, unsigned i, uint16_t value) {
    struct flash *f = ctx;
    assert(i < OLED_PAGE_BYTES && f->words[i] == UINT16_MAX);
    if (!f->budget) return 0;
    f->budget--; f->written++; f->words[i] = value;
    return 1;
}
static int erase(void *ctx, unsigned i) {
    struct flash *f = ctx;
    assert(i == 0 || i == OLED_PAGE_BYTES / 2);
    f->erased++;
    for (unsigned j = 0; j < OLED_PAGE_BYTES/2; j++) {
        if (!f->budget) return 0;
        f->budget--; f->words[i+j] = UINT16_MAX;
    }
    return 1;
}
int main(void) {
    struct flash f = {.budget = 100000};
    memset(f.words, 255, sizeof(f.words));
    struct oled_io io = {&f,read_word,program,erase};
    assert(!oled_latest(&io).valid);
    assert(!oled_store(&io, oled_latest(&io), 0));
    assert(!oled_store(&io, oled_latest(&io), 0x0201));
    assert(!oled_store(&io, oled_latest(&io), 0x013d));
    for (unsigned i = 0; i < OLED_SLOTS; i++) {
        uint16_t pair = i % 2 ? 0x013c : 0x3c3c;
        assert(oled_store(&io, oled_latest(&io), pair));
        assert(oled_latest(&io).pair == pair);
        int count = f.written;
        assert(oled_store(&io, oled_latest(&io), pair) && f.written == count);
    }
    assert(!f.erased);
    const struct flash original = f;
    const uint16_t before = oled_latest(&io).pair, after = 0x0101;
    for (int cut = 0; cut <= (int)OLED_PAGE_BYTES/2+9; cut++) {
        f = original; f.budget = cut;
        int complete = oled_store(&io, oled_latest(&io), after);
        struct oled_entry recovered = oled_latest(&io);
        assert(recovered.valid && recovered.pair == (complete ? after : before));
        f.budget = 100000;
        assert(oled_store(&io, recovered, after));
        assert(oled_latest(&io).pair == after);
    }
    return 0;
}
