// M300 Classic OEM print counter, GPL-3.0-or-later.
#include <string.h>
#include "m300_factory_counter.h"

#define PAGE M300_FACTORY_NVM_SIZE
#define ACTIVE 0u
#define ERASED UINT16_MAX
#define ID_COUNT 7u
#define BODY_WORDS 23u
#define ERASE_MARKER 8u

// OEM 1.3.1 records start at +4. Keep +2 erased, as on stock pages.
static const uint8_t payload_words[ID_COUNT] = {2, 1, 1, 1, 1, 2, 2};

struct page_image {
    uint16_t header, values[ID_COUNT][2];
    uint8_t present, valid;
};

static uint16_t
read_word(const struct m300_counter_io *io, unsigned offset)
{
    return io->read(io->context, offset);
}

static int
erased_tail(const struct m300_counter_io *io, unsigned start, unsigned end)
{
    for (unsigned offset = start; offset < end; offset += 2)
        if (read_word(io, offset) != ERASED)
            return 0;
    return 1;
}

static void
scan(const struct m300_counter_io *io, unsigned base, struct page_image *image)
{
    memset(image, 0, sizeof(*image));
    image->header = read_word(io, base);
    if (read_word(io, base + 2) != ERASED)
        return;
    unsigned end = base + PAGE;
    for (unsigned offset = base + 4; offset < end;) {
        unsigned id = read_word(io, offset);
        if (id == ERASED) {
            if (!erased_tail(io, offset + 2, end))
                return;
            break;
        }
        offset += 2;
        if (id >= ID_COUNT || 2 * payload_words[id] > end - offset)
            return;
        for (unsigned i = 0; i < payload_words[id]; i++, offset += 2)
            image->values[id][i] = read_word(io, offset);
        if (id == 0 && image->values[0][0] == ERASED
            && image->values[0][1] == ERASED)
            return;
        image->present |= 1u << id;
    }
    image->valid = !!(image->present & 1u);
}

static uint32_t
minutes(const struct page_image *image)
{
    return image->values[0][0] | ((uint32_t)image->values[0][1] << 16);
}

static uint32_t
crc_byte(uint32_t crc, uint8_t value)
{
    crc ^= value;
    for (unsigned i = 0; i < 8; i++)
        crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    return crc;
}

static uint32_t
settings_crc(const struct page_image *image)
{
    uint32_t crc = UINT32_MAX;
    for (unsigned id = 1; id < ID_COUNT; id++) {
        unsigned present = (image->present >> id) & 1u;
        crc = crc_byte(crc, id);
        crc = crc_byte(crc, present);
        if (!present)
            continue;
        for (unsigned i = 0; i < payload_words[id]; i++) {
            uint16_t value = image->values[id][i];
            crc = crc_byte(crc, value);
            crc = crc_byte(crc, value >> 8);
        }
    }
    return ~crc;
}

void
m300_counter_inspect(const struct m300_counter_io *io,
                     struct m300_counter_snapshot *snapshot)
{
    *snapshot = (struct m300_counter_snapshot){
        .source = M300_FACTORY_COUNTER_NO_BANK,
    };
    for (unsigned page = 0; page < 2; page++) {
        unsigned base = page * PAGE;
        if (read_word(io, base) != ACTIVE)
            continue;
        struct page_image image;
        scan(io, base, &image);
        if (!image.valid)
            continue;
        snapshot->state = M300_COUNTER_RECOVERY_REQUIRED;
        unsigned other = (1u - page) * PAGE;
        if (erased_tail(io, other, other + PAGE)) {
            snapshot->state = M300_COUNTER_NORMALIZED;
            snapshot->source = page;
            snapshot->minutes = minutes(&image);
            snapshot->settings_crc = settings_crc(&image);
            return;
        }
    }
}

static unsigned
make_body(uint16_t body[BODY_WORDS], const struct page_image *image,
          uint32_t expected, uint32_t target)
{
    // An earlier OEM record carries a one-way authorization to erase the old
    // page. Program its high halfword to zero only after checking both pages.
    // OEM reads the final ID0, so this marker and the prior counter are ignored.
    // A zero low halfword also accommodates the OEM transfer recovery's +6
    // comparison if a complete staged page is ever marked RECEIVING.
    unsigned words = 0;
    body[words++] = 0;
    body[words++] = 0;
    body[words++] = ERASED;
    // The previous ID0 value remains readable by a service decoder even
    // after the old page is erased. OEM reads the final occurrence of ID0.
    body[words++] = 0;
    body[words++] = expected;
    body[words++] = expected >> 16;
    for (unsigned id = 1; id < ID_COUNT; id++) {
        if (!(image->present & (1u << id)))
            continue;
        body[words++] = id;
        for (unsigned i = 0; i < payload_words[id]; i++)
            body[words++] = image->values[id][i];
    }
    body[words++] = 0;
    body[words++] = target;
    body[words++] = target >> 16;
    return words;
}

static int
body_matches(const struct m300_counter_io *io, unsigned base,
             const uint16_t body[BODY_WORDS], unsigned words)
{
    if (read_word(io, base + 2) != ERASED)
        return 0;
    for (unsigned i = 0; i < words; i++) {
        unsigned offset = 4 + 2 * i;
        if (offset != ERASE_MARKER
            && read_word(io, base + offset) != body[i])
            return 0;
    }
    return erased_tail(io, base + 4 + 2 * words, base + PAGE);
}

static int
program(const struct m300_counter_io *io, unsigned offset, uint16_t value)
{
    return io->write_allowed(io->context)
        && io->program(io->context, offset, value)
        && read_word(io, offset) == value;
}

static int
erase(const struct m300_counter_io *io, unsigned base)
{
    if (erased_tail(io, base, base + PAGE))
        return 1;
    return io->write_allowed(io->context) && io->erase(io->context, base)
        && erased_tail(io, base, base + PAGE);
}

enum m300_counter_result
m300_counter_commit(const struct m300_counter_io *io, unsigned source,
                    uint32_t expected, uint32_t target, uint32_t fingerprint)
{
    if (source > 1 || target == UINT32_MAX || target <= expected)
        return M300_COUNTER_INVALID_TARGET;
    unsigned old = source * PAGE, next = (1u - source) * PAGE;
    struct page_image original, receiver;
    scan(io, old, &original);
    scan(io, next, &receiver);
    int original_matches = original.valid && original.header == ACTIVE
        && minutes(&original) == expected
        && settings_crc(&original) == fingerprint;
    uint16_t body[BODY_WORDS];
    unsigned words = 0;
    if (receiver.valid && minutes(&receiver) == target
        && settings_crc(&receiver) == fingerprint)
        words = make_body(body, &receiver, expected, target);
    uint16_t marker = read_word(io, next + ERASE_MARKER);
    int receiver_matches = words && body_matches(io, next, body, words);

    if (receiver_matches && receiver.header == ACTIVE && !marker) {
        // The destination was verified and the old page already authorized
        // for erase. A torn old erase can leave a valid-looking header/body.
        if (erased_tail(io, old, old + PAGE))
            return M300_COUNTER_ALREADY_APPLIED;
        if (!io->write_allowed(io->context))
            return M300_COUNTER_NOT_QUIESCENT;
        return erase(io, old) ? M300_COUNTER_APPLIED : M300_COUNTER_IO_ERROR;
    }
    if (!io->write_allowed(io->context))
        return M300_COUNTER_NOT_QUIESCENT;
    if (!original_matches)
        return original.valid && original.header == ACTIVE
            ? M300_COUNTER_CONFLICT : M300_COUNTER_INVALID_BANKS;

    words = make_body(body, &original, expected, target);
    if (!body_matches(io, next, body, words)) {
        // A stock RECEIVING page is not ours unless the exact prepared bytes
        // match. A dirty ERASED page may be a cut while staging this transaction.
        if (receiver.header != ERASED)
            return M300_COUNTER_INVALID_BANKS;
        if (!erase(io, next))
            return M300_COUNTER_IO_ERROR;
        for (unsigned i = 0; i < words; i++)
            if (body[i] != ERASED && !program(io, next + 4 + 2 * i, body[i]))
                return M300_COUNTER_IO_ERROR;
    }
    if (!body_matches(io, next, body, words)
        || (receiver.header != ACTIVE && !program(io, next, ACTIVE))
        || !body_matches(io, next, body, words)
        || !program(io, next + ERASE_MARKER, 0)
        || !body_matches(io, next, body, words))
        return M300_COUNTER_IO_ERROR;

    // Flash cannot change the old header 0000 to FFFF without an erase.
    // A power cut here needs this same transaction to normalize both banks
    // before running stock firmware, which can format two active pages.
    return erase(io, old) ? M300_COUNTER_APPLIED : M300_COUNTER_IO_ERROR;
}
