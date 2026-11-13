// SPDX-License-Identifier: GPL-3.0-or-later
// Classic M300 private SPI1 SD reader. No WRITE, Flash or raw-SPI commands.
// The wire state machine clocks at most 32 bytes per 1 ms task activation.
#ifndef M300_SD_TEST
#include "autoconf.h"
#include "board/io.h"
#include "board/misc.h"
#include "command.h"
#include "internal.h"
#include "sched.h"
#endif
#include "m300_sched.h"

DECL_CONSTANT_STR("RESERVE_PINS_m300_sd", "PA4,PA5,PA6,PA7");
DECL_CONSTANT("M300_SD_ABI", 1);
DECL_CONSTANT("M300_SD_READ_ONLY", 1);
DECL_CONSTANT("M300_SD_MAX_CHUNK", 32);
DECL_CONSTANT("M300_SD_TASK_BYTES", 32);
DECL_CONSTANT("M300_SD_POLL_US", 1000);

enum sd_state { SD_IDLE, SD_POWER, SD_LEAD, SD_SELECT, SD_PACKET,
                SD_RESPONSE, SD_EXTRA, SD_DATA_WAIT, SD_DATA, SD_CRC_HIGH,
                SD_CRC_LOW, SD_TRAILER };
enum sd_phase { PH_RESET, PH_IFCOND, PH_APP, PH_OPCOND, PH_OCR,
                PH_BLOCKLEN, PH_CID, PH_CSD, PH_READ };
enum sd_error { SD_OK, SD_TIMEOUT, SD_SPI, SD_COMMAND, SD_TOKEN,
                SD_CRC, SD_CAPACITY, SD_SESSION, SD_BUSY, SD_RANGE };

static uint8_t configured, sd_fault, sd_ready, sd_active, high_capacity, v2;
static uint8_t state, phase, packet[6], extra[4], cid[16], csd[16];
static uint8_t sd_buffer[512], packet_pos, extra_pos, response, extra_count;
static uint16_t data_pos, data_length, crc, received_crc;
static uint32_t spi_cr1, fast_cr1, session, request_token, cached_token;
static uint32_t block_count, deadline, poll_ticks, power_count, last_chunk;
static struct timer sd_timer;
static struct task_wake sd_wake;

int
m300_factory_sd_timer(const struct timer *timer)
{
    return timer == &sd_timer && !sd_active;
}

int
m300_factory_sd_idle(void)
{
    return !sd_active;
}

static void
sd_put(unsigned pin, unsigned value)
{
    writel((void *)&GPIOA->BSRR, (1u << pin) << (value ? 0 : 16));
}

static void
sd_mode(unsigned pin, unsigned nibble)
{
    unsigned shift = pin * 4;
    GPIOA->CRL = (GPIOA->CRL & ~(15u << shift)) | (nibble << shift);
}

void
m300_sd_init(void)
{
    RCC->APB2ENR |= (1u << 2);
    (void)RCC->APB2ENR;
    sd_put(4, 1);
    sd_mode(4, 2);
    // SCK/MOSI are left as inputs until explicit private configuration.
}
DECL_INIT(m300_sd_init);

static uint16_t
sd_crc16(uint16_t value, uint8_t byte)
{
    value ^= (uint16_t)byte << 8;
    for (uint8_t i = 0; i < 8; i++)
        value = (value << 1) ^ ((value & 0x8000) ? 0x1021 : 0);
    return value;
}

static uint8_t
sd_wait(uint32_t mask, uint32_t value)
{
    uint32_t end = timer_read_time() + timer_from_us(100);
    while ((SPI1->SR & mask) != value)
        if (!timer_is_before(timer_read_time(), end))
            return 0;
    return 1;
}

static uint8_t
sd_xfer(uint8_t out, uint8_t *in)
{
    // No IRQ mask surrounds transfer/waits: step and watchdog IRQs stay live.
    if (SPI1->CR1 != spi_cr1)
        shutdown("M300 SD SPI ownership lost");
    if (!sd_wait(1u << 1, 1u << 1))
        return 0;
    writew((void *)&SPI1->DR, out);
    if (!sd_wait(1u, 1u))
        return 0;
    *in = readw((void *)&SPI1->DR);
    return sd_wait(1u << 7, 0);
}

static void
sd_finish(uint8_t error)
{
    sd_put(4, 1);
    sd_active = 0;
    state = SD_IDLE;
    if (error) {
        sd_ready = 0;
        cached_token = 0;
    }
    uint8_t info[32];
    uint8_t length = 0;
    if (!error && phase == PH_CSD) {
        for (uint8_t i = 0; i < 16; i++) {
            info[i] = cid[i];
            info[i + 16] = csd[i];
        }
        length = 32;
    }
    sendf("m300_sd_done session=%u token=%u error=%c blocks=%u data=%*s",
          session, request_token, error, block_count, length, info);
}

static void
sd_begin(uint8_t cmd, uint32_t arg, uint8_t next_phase)
{
    phase = next_phase;
    packet[0] = 0x40 | cmd;
    packet[1] = arg >> 24;
    packet[2] = arg >> 16;
    packet[3] = arg >> 8;
    packet[4] = arg;
    packet[5] = cmd == 0 ? 0x95 : cmd == 8 ? 0x87 : 1;
    packet_pos = extra_pos = 0;
    sd_put(4, 1);
    state = SD_LEAD;
}

static uint8_t
sd_capacity(void)
{
    uint64_t blocks;
    if ((csd[0] >> 6) == 1 && high_capacity) {
        uint32_t size = ((uint32_t)(csd[7] & 63) << 16)
                        | ((uint32_t)csd[8] << 8) | csd[9];
        blocks = ((uint64_t)size + 1) << 10;
    } else if ((csd[0] >> 6) == 0 && !high_capacity) {
        uint32_t size = ((uint32_t)(csd[6] & 3) << 10)
                        | ((uint32_t)csd[7] << 2) | (csd[8] >> 6);
        uint8_t mult = ((csd[9] & 3) << 1) | (csd[10] >> 7);
        uint8_t length = csd[5] & 15;
        if (length < 9 || length > 11)
            return 0;
        blocks = ((uint64_t)size + 1) << (mult + 2 + length - 9);
    } else {
        return 0;
    }
    if (!blocks || blocks > 0xffffffffu
        || (!high_capacity && blocks > 0x800000u))
        return 0;
    block_count = blocks;
    return 1;
}

static void
sd_continue(void)
{
    switch (phase) {
    case PH_RESET:
        if (response != 1) { sd_finish(SD_COMMAND); return; }
        sd_begin(8, 0x1aa, PH_IFCOND);
        return;
    case PH_IFCOND:
        if (response == 1) {
            if (extra[0] || extra[1] || extra[2] != 1 || extra[3] != 0xaa) {
                sd_finish(SD_COMMAND); return;
            }
            v2 = 1;
        } else if (response != 5) {
            sd_finish(SD_COMMAND); return;
        }
        sd_begin(55, 0, PH_APP);
        return;
    case PH_APP:
        if (response > 1) { sd_finish(SD_COMMAND); return; }
        sd_begin(41, v2 ? 0x40000000 : 0, PH_OPCOND);
        return;
    case PH_OPCOND:
        if (response == 1) { sd_begin(55, 0, PH_APP); return; }
        if (response) { sd_finish(SD_COMMAND); return; }
        sd_begin(58, 0, PH_OCR);
        return;
    case PH_OCR:
        if (response || !(extra[0] & 0x80)
            || !(extra[1] & 0x30)) {
            sd_finish(SD_COMMAND); return;
        }
        high_capacity = v2 && (extra[0] & 0x40);
        if (!high_capacity) { sd_begin(16, 512, PH_BLOCKLEN); return; }
        // fall through
    case PH_BLOCKLEN:
        if (response) { sd_finish(SD_COMMAND); return; }
        SPI1->CR1 &= ~(1u << 6);
        spi_cr1 = fast_cr1;
        SPI1->CR1 = spi_cr1;
        sd_begin(10, 0, PH_CID);
        return;
    case PH_CID:
        for (uint8_t i = 0; i < 16; i++) cid[i] = sd_buffer[i];
        sd_begin(9, 0, PH_CSD);
        return;
    case PH_CSD:
        for (uint8_t i = 0; i < 16; i++) csd[i] = sd_buffer[i];
        if (!sd_capacity()) { sd_finish(SD_CAPACITY); return; }
        sd_ready = 1;
        sd_finish(SD_OK);
        return;
    case PH_READ:
        cached_token = request_token;
        sd_finish(SD_OK);
        return;
    default:
        sd_finish(SD_COMMAND);
    }
}

static void
sd_response_done(void)
{
    if (phase == PH_CID || phase == PH_CSD || phase == PH_READ) {
        if (response) { sd_finish(SD_COMMAND); return; }
        data_length = phase == PH_READ ? 512 : 16;
        data_pos = crc = 0;
        state = SD_DATA_WAIT;
    } else if ((phase == PH_IFCOND && response == 1)
               || (phase == PH_OCR && response == 0)) {
        extra_pos = 0;
        extra_count = 4;
        state = SD_EXTRA;
    } else {
        sd_put(4, 1);
        state = SD_TRAILER;
    }
}

static void
sd_step(void)
{
    uint8_t in, out = state == SD_PACKET ? packet[packet_pos] : 0xff;
    if (!sd_xfer(out, &in)) { sd_finish(SD_SPI); return; }
    switch (state) {
    case SD_POWER:
        if (++power_count == 10) sd_begin(0, 0, PH_RESET);
        break;
    case SD_LEAD:
        sd_put(4, 0);
        state = SD_SELECT;
        break;
    case SD_SELECT:
        if (in == 0xff) state = SD_PACKET;
        break;
    case SD_PACKET:
        if (++packet_pos == 6) state = SD_RESPONSE;
        break;
    case SD_RESPONSE:
        if (!(in & 0x80)) { response = in; sd_response_done(); }
        break;
    case SD_EXTRA:
        extra[extra_pos++] = in;
        if (extra_pos == extra_count) { sd_put(4, 1); state = SD_TRAILER; }
        break;
    case SD_DATA_WAIT:
        if (in == 0xfe) state = SD_DATA;
        else if (in != 0xff) sd_finish(SD_TOKEN);
        break;
    case SD_DATA:
        sd_buffer[data_pos++] = in;
        crc = sd_crc16(crc, in);
        if (data_pos == data_length) state = SD_CRC_HIGH;
        break;
    case SD_CRC_HIGH:
        received_crc = (uint16_t)in << 8;
        state = SD_CRC_LOW;
        break;
    case SD_CRC_LOW:
        received_crc |= in;
        if (received_crc != crc) { sd_finish(SD_CRC); return; }
        sd_put(4, 1);
        state = SD_TRAILER;
        break;
    case SD_TRAILER:
        sd_continue();
        break;
    default:
        sd_finish(SD_COMMAND);
    }
}

static uint_fast8_t
sd_event(struct timer *timer)
{
    uint8_t active = sd_active;
    if (active) sched_wake_task(&sd_wake);
    // 1 ms during an SD transaction; 5 ms idle avoids needless IRQ work
    // during Z homing. New transactions may wait at most one idle interval.
    uint32_t period = active ? poll_ticks : timer_from_us(5000);
    timer->waketime = m300_next_timer(timer->waketime, timer_read_time(),
                                      period);
    return SF_RESCHEDULE;
}

void
command_m300_sd_config(uint32_t *args)
{
    uint32_t rate = args[0];
    if (configured || sd_fault || rate < 500000 || rate > 2000000)
        shutdown("M300 invalid SD config");
    RCC->APB2ENR |= (1u << 2) | (1u << 12);
    RCC->APB2RSTR |= 1u << 12;
    RCC->APB2RSTR &= ~(1u << 12);
    sd_put(4, 1); sd_mode(4, 2);
    sd_put(5, 0); sd_mode(5, 0xb);
    sd_put(6, 1); sd_mode(6, 8);
    sd_put(7, 1); sd_mode(7, 0xb);
    SPI1->CR1 = SPI1->CR2 = 0;
    uint32_t pclk = get_pclock_frequency((uint32_t)SPI1), div = 0;
    while ((pclk >> (div + 1)) > rate && div < 7) div++;
    fast_cr1 = (div << 3) | (1u << 2) | (1u << 6) | (1u << 8) | (1u << 9);
    // APB2=72 MHz /256 =281250 Hz, within SD initialization limit.
    spi_cr1 = (fast_cr1 & ~(7u << 3)) | (7u << 3);
    if ((pclk >> 8) > 400000) shutdown("M300 SD init clock too fast");
    SPI1->CR1 = spi_cr1;
    poll_ticks = timer_from_us(1000);
    sd_timer.func = sd_event;
    sd_timer.waketime = timer_read_time() + poll_ticks;
    configured = 1;
    sched_add_timer(&sd_timer);
}
DECL_COMMAND(command_m300_sd_config, "m300_sd_config rate=%u");

static void
sd_reject(uint32_t rejected_session, uint32_t token, uint8_t error)
{
    sendf("m300_sd_done session=%u token=%u error=%c blocks=%u data=%*s",
          rejected_session, token, error, block_count, 0, sd_buffer);
}

void
command_m300_sd_open(uint32_t *args)
{
    if (!configured || sd_fault) shutdown("M300 SD not configured");
    if (!args[0] || !args[1]) { sd_reject(args[0], args[1], SD_SESSION); return; }
    if (sd_active) { sd_reject(args[0], args[1], SD_BUSY); return; }
    sd_ready = cached_token = block_count = v2 = high_capacity = 0;
    session = args[0]; request_token = args[1];
    sd_put(4, 1);
    // A previous peripheral timeout may have left RXNE/OVR pending. A private
    // SPI1 reset gives a new card session fresh hardware state without touching
    // the card, GPIOA's unrelated pins, SPI2/OLED, heaters or motion.
    RCC->APB2RSTR |= 1u << 12;
    RCC->APB2RSTR &= ~(1u << 12);
    SPI1->CR1 = SPI1->CR2 = 0;
    spi_cr1 = (fast_cr1 & ~(7u << 3)) | (7u << 3);
    SPI1->CR1 = spi_cr1;
    state = SD_POWER; phase = PH_RESET; power_count = 0;
    deadline = timer_read_time() + timer_from_us(5000000);
    sd_active = 1;
}
DECL_COMMAND(command_m300_sd_open, "m300_sd_open session=%u token=%u");

void
command_m300_sd_read(uint32_t *args)
{
    if (!configured || sd_fault) shutdown("M300 SD not configured");
    uint32_t lba = args[2];
    if (sd_active) { sd_reject(args[0], args[1], SD_BUSY); return; }
    if (!sd_ready || args[0] != session || !args[1]) {
        sd_reject(args[0], args[1], SD_SESSION); return;
    }
    if (lba >= block_count || (!high_capacity && lba > 0x7fffff)) {
        sd_reject(args[0], args[1], SD_RANGE); return;
    }
    request_token = args[1]; cached_token = 0;
    deadline = timer_read_time() + timer_from_us(1000000);
    sd_begin(17, high_capacity ? lba : lba << 9, PH_READ);
    sd_active = 1;
}
DECL_COMMAND(command_m300_sd_read, "m300_sd_read session=%u token=%u lba=%u");

void
command_m300_sd_chunk(uint32_t *args)
{
    if (!configured || sd_fault) shutdown("M300 SD not configured");
    uint32_t offset = args[3], length = args[4];
    if (!sd_ready || sd_active || args[0] != session || !args[1]
        || !cached_token || args[2] != cached_token) {
        sd_reject(args[0], args[1], SD_SESSION); return;
    }
    if (!length || length > 32 || offset > 512 || length > 512 - offset) {
        sd_reject(args[0], args[1], SD_RANGE); return;
    }
    last_chunk = args[1];
    sendf("m300_sd_data session=%u token=%u offset=%hu data=%*s",
          session, last_chunk, offset, length, sd_buffer + offset);
}
DECL_COMMAND(command_m300_sd_chunk,
             "m300_sd_chunk session=%u token=%u read_token=%u offset=%hu count=%c");

void
command_m300_sd_close(uint32_t *args)
{
    if (!configured || sd_fault) shutdown("M300 SD not configured");
    if (args[0] != session) { sd_reject(args[0], args[1], SD_SESSION); return; }
    sd_put(4, 1);
    sd_ready = sd_active = cached_token = 0;
    request_token = args[1]; state = SD_IDLE;
    sd_reject(session, request_token, SD_OK);
}
DECL_COMMAND(command_m300_sd_close, "m300_sd_close session=%u token=%u");

void
m300_sd_shutdown(void)
{
    sd_fault = 1;
    sd_active = sd_ready = 0;
    cached_token = 0;
    RCC->APB2ENR |= 1u << 2;
    sd_put(4, 1);
    if (configured) SPI1->CR1 &= ~(1u << 6);
}
DECL_SHUTDOWN(m300_sd_shutdown);

void
m300_sd_task(void)
{
    if (!sched_check_wake(&sd_wake) || !sd_active || sd_fault) return;
    if (!timer_is_before(timer_read_time(), deadline)) {
        sd_finish(SD_TIMEOUT); return;
    }
    for (uint8_t budget = 0; budget < 32 && sd_active; budget++) sd_step();
}
DECL_TASK(m300_sd_task);
