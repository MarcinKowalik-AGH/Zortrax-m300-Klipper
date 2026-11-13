// Test the exact MCU transaction core with STM32F103 Flash programming rules.
// GPL-3.0-or-later.
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../overlay/src/stm32/m300_factory_counter.h"

#define PAGE M300_FACTORY_NVM_SIZE
#define SIZE M300_FACTORY_COUNTER_SPAN
#define EXPECTED 286732u
#define TARGET 287156u

enum fault_style {
    BEFORE_OPERATION,
    AFTER_OPERATION,
    PARTIAL_PREFIX,
    PARTIAL_BITS,
};

struct flash {
    uint8_t memory[SIZE + PAGE];
    unsigned source, ops, cut, salt;
    enum fault_style style;
    int allowed;
};

static void
set_word(struct flash *flash, unsigned offset, uint16_t value)
{
    flash->memory[offset] = value;
    flash->memory[offset + 1] = value >> 8;
}

static uint16_t
read_word(void *context, unsigned offset)
{
    struct flash *flash = context;
    assert(offset < SIZE && offset % 2 == 0);
    return flash->memory[offset] | ((uint16_t)flash->memory[offset + 1] << 8);
}

static int
should_fail(struct flash *flash)
{
    return ++flash->ops == flash->cut;
}

static unsigned
next_bits(unsigned *seed)
{
    *seed = *seed * 1664525u + 1013904223u;
    return *seed >> 16;
}

static int
program(void *context, unsigned offset, uint16_t value)
{
    struct flash *flash = context;
    assert(offset < SIZE && offset % 2 == 0);
    unsigned old = flash->source * PAGE;
    assert(offset / PAGE != flash->source);
    assert(read_word(flash, old) == 0);
    uint16_t before = read_word(flash, offset);
    assert(before == UINT16_MAX || value == 0);
    if (!should_fail(flash)) {
        set_word(flash, offset, value);
        return 1;
    }
    if (flash->style == AFTER_OPERATION) {
        set_word(flash, offset, value);
    } else if (flash->style >= PARTIAL_PREFIX) {
        uint16_t mask = flash->style == PARTIAL_PREFIX
            ? 0xff00u : next_bits(&flash->salt);
        set_word(flash, offset, before & (value | mask));
    }
    return 0;
}

static int
erase(void *context, unsigned offset)
{
    struct flash *flash = context;
    assert(offset == 0 || offset == PAGE);
    unsigned active = (offset / PAGE == flash->source ? 1 - flash->source
                       : flash->source) * PAGE;
    assert(read_word(flash, active) == 0);
    int fail = should_fail(flash);
    if (!fail || flash->style == AFTER_OPERATION) {
        memset(flash->memory + offset, 0xff, PAGE);
    } else if (flash->style == PARTIAL_PREFIX) {
        memset(flash->memory + offset, 0xff, flash->salt % PAGE);
    } else if (flash->style == PARTIAL_BITS) {
        // Keep ACTIVE sometimes, including when an earlier or the latest
        // record is partly erased and still parses.
        for (unsigned i = flash->salt % 4; i < 100; i++)
            flash->memory[offset + i] |= next_bits(&flash->salt);
    }
    return !fail;
}

static int
allowed(void *context)
{
    return ((struct flash *)context)->allowed;
}

static struct m300_counter_io
flash_io(struct flash *flash)
{
    return (struct m300_counter_io){
        .context = flash,
        .read = read_word,
        .program = program,
        .erase = erase,
        .write_allowed = allowed,
    };
}

static void
init(struct flash *flash, unsigned source)
{
    *flash = (struct flash){.source = source, .allowed = 1};
    memset(flash->memory, 0xff, SIZE);
    memset(flash->memory + SIZE, 0x5a, PAGE);
    const uint16_t records[] = {
        0, 0xffff, 0, 2, 0,
        1, 0x1111, 2, 0xffff, 3, 0x3333, 4, 0x4444,
        5, 0x5555, 0x6655, 6, 0xffff, 0x6666, 1, 0x1112,
        0, EXPECTED & 0xffff, EXPECTED >> 16,
    };
    for (unsigned i = 0; i < sizeof(records) / sizeof(records[0]); i++)
        set_word(flash, source * PAGE + 2 * i, records[i]);
}

static struct m300_counter_snapshot
inspect(struct flash *flash)
{
    struct m300_counter_snapshot snapshot;
    struct m300_counter_io io = flash_io(flash);
    m300_counter_inspect(&io, &snapshot);
    return snapshot;
}

static enum m300_counter_result
commit(struct flash *flash, uint32_t expected, uint32_t target, uint32_t crc)
{
    struct m300_counter_io io = flash_io(flash);
    return m300_counter_commit(&io, flash->source, expected, target, crc);
}

static void
verify(struct flash *flash, unsigned source, uint32_t expected,
       uint32_t target, uint32_t crc)
{
    struct m300_counter_snapshot snapshot = inspect(flash);
    assert(snapshot.state == M300_COUNTER_NORMALIZED);
    assert(snapshot.source == source && snapshot.minutes == target);
    assert(snapshot.settings_crc == crc);
    unsigned base = source * PAGE;
    assert(read_word(flash, base + 4) == 0);
    assert(read_word(flash, base + 6) == 0);
    assert(read_word(flash, base + 8) == 0);
    assert(read_word(flash, base + 10) == 0);
    assert(read_word(flash, base + 12) == (uint16_t)expected);
    assert(read_word(flash, base + 14) == expected >> 16);
    uint32_t stock_minutes = 0;
    assert(m300_factory_minutes(flash->memory, flash->memory + PAGE,
                                &stock_minutes));
    assert(stock_minutes == target);
    for (unsigned i = SIZE; i < sizeof(flash->memory); i++)
        assert(flash->memory[i] == 0x5a);
}

static unsigned
test_cuts(unsigned source)
{
    struct flash flash;
    init(&flash, source);
    uint32_t crc = inspect(&flash).settings_crc;
    struct flash initial = flash;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_APPLIED);
    unsigned operations = flash.ops, cases = 0;
    verify(&flash, 1 - source, EXPECTED, TARGET, crc);

    for (unsigned cut = 1; cut <= operations; cut++) {
        for (enum fault_style style = BEFORE_OPERATION;
             style <= PARTIAL_BITS; style++) {
            for (unsigned salt = 1; salt < 5; salt++) {
                flash = initial;
                flash.cut = cut;
                flash.style = style;
                flash.salt = salt * 519u;
                assert(commit(&flash, EXPECTED, TARGET, crc)
                       == M300_COUNTER_IO_ERROR);
                if (read_word(&flash, (1 - source) * PAGE) != 0)
                    assert(memcmp(flash.memory + source * PAGE,
                                  initial.memory + source * PAGE, PAGE) == 0);
                assert(inspect(&flash).state != M300_COUNTER_UNAVAILABLE);
                flash.cut = 0;
                enum m300_counter_result status =
                    commit(&flash, EXPECTED, TARGET, crc);
                assert(status == M300_COUNTER_APPLIED
                       || status == M300_COUNTER_ALREADY_APPLIED);
                verify(&flash, 1 - source, EXPECTED, TARGET, crc);
                unsigned used = flash.ops;
                flash.allowed = 0;
                assert(commit(&flash, EXPECTED, TARGET, crc)
                       == M300_COUNTER_ALREADY_APPLIED);
                assert(flash.ops == used);
                cases++;
            }
        }
    }

    // An already dirty inactive bank can itself tear while being erased.
    for (unsigned style = 0; style <= PARTIAL_BITS; style++) {
        flash = initial;
        set_word(&flash, (1 - source) * PAGE + 4, 1234);
        flash.cut = 1;
        flash.style = style;
        assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_IO_ERROR);
        assert(memcmp(flash.memory + source * PAGE,
                      initial.memory + source * PAGE, PAGE) == 0);
        flash.cut = 0;
        assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_APPLIED);
        verify(&flash, 1 - source, EXPECTED, TARGET, crc);
        cases++;
    }
    return cases;
}

static void
test_alternating_and_conflicts(void)
{
    struct flash flash;
    init(&flash, 0);
    uint32_t crc = inspect(&flash).settings_crc;
    assert(commit(&flash, EXPECTED + 1, TARGET, crc) == M300_COUNTER_CONFLICT);
    assert(commit(&flash, EXPECTED, TARGET, crc ^ 1) == M300_COUNTER_CONFLICT);
    assert(commit(&flash, EXPECTED, UINT32_MAX, crc)
           == M300_COUNTER_INVALID_TARGET);
    assert(flash.ops == 0);
    flash.allowed = 0;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_NOT_QUIESCENT);
    assert(flash.ops == 0);
    flash.allowed = 1;
    // Other settings and foreign transfer layouts require inspection first.
    set_word(&flash, PAGE, 0xeeee);
    assert(commit(&flash, EXPECTED, TARGET, crc)
           == M300_COUNTER_INVALID_BANKS);
    assert(flash.ops == 0);
    set_word(&flash, PAGE, 0xffff);
    for (uint32_t next = EXPECTED + 1; next <= EXPECTED + 100; next++) {
        assert(commit(&flash, next - 1, next, crc) == M300_COUNTER_APPLIED);
        flash.source = 1 - flash.source;
        verify(&flash, flash.source, next - 1, next, crc);
    }
}

static void
test_changed_id_after_erase_started(unsigned source)
{
    struct flash flash;
    init(&flash, source);
    unsigned old = source * PAGE;
    // Replace old ID3 with another valid-width record. Now a torn erase can
    // turn the first ID1 into the previously absent ID3 by setting one bit.
    set_word(&flash, old + 18, 4);
    uint32_t crc = inspect(&flash).settings_crc;
    struct flash original = flash;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_APPLIED);
    unsigned old_erase_op = flash.ops;
    flash = original;
    flash.cut = old_erase_op;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_IO_ERROR);
    set_word(&flash, old + 10, 3);
    flash.cut = 0;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_APPLIED);
    verify(&flash, 1 - source, EXPECTED, TARGET, crc);

    // Before erase authorization, a changed source must cause zero writes.
    flash = original;
    flash.cut = old_erase_op - 1;
    flash.style = PARTIAL_PREFIX;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_IO_ERROR);
    set_word(&flash, old + 10, 3);
    flash.cut = 0;
    unsigned operations = flash.ops;
    assert(commit(&flash, EXPECTED, TARGET, crc) == M300_COUNTER_CONFLICT);
    assert(flash.ops == operations);
}

int
main(void)
{
    unsigned cases = test_cuts(0) + test_cuts(1);
    test_alternating_and_conflicts();
    test_changed_id_after_erase_started(0);
    test_changed_id_after_erase_started(1);
    printf("PASS M300 factory counter power cuts=%u, alternating writes=100\n",
           cases);
    return 0;
}
