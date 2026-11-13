// M300 factory identity and bounded stock-compatible print counter writer.
// GPL-3.0-or-later.
#include "board/irq.h"
#include "board/misc.h"
#include "command.h"
#include "internal.h"
#include "m300.h"
#include "m300_factory.h"
#include "m300_factory_counter.h"

DECL_CONSTANT("M300_FACTORY_ABI", M300_FACTORY_ABI);
DECL_CONSTANT("M300_FACTORY_HW_ADDRESS", M300_FACTORY_HW_ADDRESS);
DECL_CONSTANT("M300_FACTORY_INFO_ABI", M300_FACTORY_INFO_ABI);
DECL_CONSTANT("M300_FACTORY_COUNTER_ABI", M300_FACTORY_COUNTER_ABI);
DECL_CONSTANT("M300_FACTORY_COUNTER_RUNTIME_ABI", 1);

// The high-density, 256 KiB F103 uses the two specified 2 KiB Flash pages.
// The next page (0x0803F800) retains the factory ID/serial and is read-only.
#define FLASH_SIZE_WORD 0x1ffff7e0u
#define STM32F103_HIGH_DENSITY_ID 0x414u
#define M300_FLASH_KEY1 0x45670123u
#define M300_FLASH_KEY2 0xcdef89abu
#define FLASH_STATUS_BITS (FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPRTERR)
#define ERASE_TIMEOUT_US 45000u // DS5792: 2 KiB page erase max. 40 ms.
#define PROGRAM_TIMEOUT_US 500u // DS5792: halfword program max. 70 us.
#define ERASE_MARGIN_US 47000u
#define PROGRAM_MARGIN_US 1000u
#define RUNTIME_START_MARGIN_US 5000u
#define RUNTIME_STAGE_MARGIN_US (ERASE_MARGIN_US + 15000u)
#define RUNTIME_MAX_DEADLINE_US 400000u
#define RUNTIME_WAIT_US 45000u

_Static_assert(M300_FACTORY_NVM_A_ADDRESS + M300_FACTORY_NVM_SIZE
               == M300_FACTORY_NVM_B_ADDRESS, "noncontiguous NVM banks");
_Static_assert(M300_FACTORY_NVM_B_ADDRESS + M300_FACTORY_NVM_SIZE
               == 0x0803f800u, "NVM banks overlap factory identity");

extern int m300_native_config_started(void);
extern int m300_factory_steppers_idle(void);
extern int m300_factory_heaters_idle(void);
extern int m300_factory_panel_idle(void);
extern int m300_factory_sd_idle(void);
extern int32_t m300_factory_timer_margin(void);
extern void m300_factory_rebase_timers(void);

struct counter_window {
    uint32_t deadline, wait_until;
    uint8_t runtime, started, erased, deferred;
};

enum flash_result { FLASH_FAILED, FLASH_OK, FLASH_PLATFORM_FAULT };

static uint32_t
factory_serial(void)
{
    uint32_t header = *(volatile const uint32_t *)M300_FACTORY_SERIAL_ADDRESS;
    return m300_factory_serial(header,
        (const volatile uint8_t *)(M300_FACTORY_SERIAL_ADDRESS + 4));
}

static int
counter_write_allowed(void *context)
{
    struct counter_window *window = context;
    if (*(volatile const uint16_t *)FLASH_SIZE_WORD != 256
        || (DBGMCU->IDCODE & 0xfffu) != STM32F103_HIGH_DENSITY_ID)
        return 0;
    if (!window->runtime)
        return m300_factory_write_allowed() && !m300_native_config_started();
    int32_t remaining = (int32_t)(window->deadline - timer_read_time());
    if (remaining <= 0 || remaining > (int32_t)timer_from_us(RUNTIME_MAX_DEADLINE_US))
        return 0;
    irqstatus_t flag = irq_save();
    int allowed = m300_factory_runtime_allowed(timer_from_us(ERASE_MARGIN_US))
        && m300_factory_steppers_idle() && m300_factory_heaters_idle()
        && m300_factory_panel_idle() && m300_factory_sd_idle();
    irq_restore(flag);
    return allowed;
}

static uint16_t
counter_read(void *context, unsigned offset)
{
    if (offset >= M300_FACTORY_COUNTER_SPAN || (offset & 1u))
        return UINT16_MAX;
    return *(volatile const uint16_t *)(M300_FACTORY_NVM_A_ADDRESS + offset);
}

// PM0075: only SRAM/peripheral accesses can run while the Flash array is
// busy. The caller has verified that no steps or heater output are scheduled.
static int noinline __section(".ramfunc.m300_factory_flash")
counter_flash_op(uintptr_t address, uint16_t value, int erase,
                 uint32_t timeout)
{
    FLASH->SR = FLASH_STATUS_BITS;
    if (erase) {
        FLASH->CR = FLASH_CR_PER;
        FLASH->AR = address;
        FLASH->CR = FLASH_CR_PER | FLASH_CR_STRT;
    } else {
        FLASH->CR = FLASH_CR_PG;
        *(volatile uint16_t *)address = value;
    }
    uint32_t start = DWT->CYCCNT;
    int platform_fault = 0;
    for (;;) {
        // PE15 is a hardware safety input. Poll it while IRQ vector fetches
        // are stalled, including the final iteration after BSY drops.
        if (GPIOE->IDR & (1u << 15)) {
            GPIOD->BSRR = 1u << 30; // common driver disable
            GPIOC->BSRR = 3u << 24; // both heaters off
            GPIOE->BSRR = 3u << 13; // protective cooling
            platform_fault = 1;
        }
        if (!(FLASH->SR & FLASH_SR_BSY))
            break;
        if (DWT->CYCCNT - start >= timeout) {
            // No fetch from busy Flash and no further writes on timeout.
            SCB->AIRCR = (0x5fau << SCB_AIRCR_VECTKEY_Pos)
                | SCB_AIRCR_SYSRESETREQ_Msk;
            __DSB();
            for (;;)
                ;
        }
    }
    uint32_t status = FLASH->SR & FLASH_STATUS_BITS;
    FLASH->CR = FLASH_CR_LOCK;
    FLASH->SR = status;
    return platform_fault ? FLASH_PLATFORM_FAULT
        : status == FLASH_SR_EOP ? FLASH_OK : FLASH_FAILED;
}

static int
counter_mutate(struct counter_window *window, unsigned offset, uint16_t value, int erase)
{
    if (!counter_write_allowed(window)) {
        window->deferred = window->runtime;
        return 0;
    }
    // HSI is the FPEC programming clock even when SYSCLK uses the HSE PLL.
    RCC->CR |= RCC_CR_HSION;
    uint32_t start = timer_read_time();
    while (!(RCC->CR & RCC_CR_HSIRDY))
        if (timer_read_time() - start > timer_from_us(1000))
            return 0;

    // An erase stalls normal IRQ vectors. Honor every strict timer; only
    // audited late-safe/cosmetic callbacks may be rescheduled on return.
    int32_t margin = timer_from_us(erase ? ERASE_MARGIN_US : PROGRAM_MARGIN_US);
    // A clean destination can stage up to 24 halfwords (500 us timeout each)
    // before the old bank erase. Reserve both phases before touching Flash.
    if (window->runtime && !window->started && !erase)
        margin = timer_from_us(RUNTIME_STAGE_MARGIN_US);
    uint32_t stop = window->runtime ? window->wait_until : start + timer_from_us(100000);
    for (;;) {
        irqstatus_t flag = irq_save();
        uint32_t now = timer_read_time();
        int expired = window->runtime && ((erase && window->erased)
            || (int32_t)(window->deadline - now) < margin);
        if (expired || !counter_write_allowed(window)) {
            window->deferred = window->runtime;
            irq_restore(flag);
            return 0;
        }
        if (!(FLASH->SR & FLASH_SR_BSY) && m300_factory_timer_margin() >= margin) {
            if (FLASH->CR & FLASH_CR_LOCK) {
                FLASH->KEYR = M300_FLASH_KEY1;
                FLASH->KEYR = M300_FLASH_KEY2;
            }
            int result = FLASH_FAILED;
            if (!(FLASH->CR & FLASH_CR_LOCK)) {
                window->started = 1;
                window->erased |= erase;
                uint32_t timeout = timer_from_us(erase ? ERASE_TIMEOUT_US : PROGRAM_TIMEOUT_US);
                result = counter_flash_op(M300_FACTORY_NVM_A_ADDRESS + offset,
                                          value, erase, timeout);
                if (result == FLASH_PLATFORM_FAULT)
                    m300_factory_platform_fault();
                if (erase)
                    m300_factory_rebase_timers();
            }
            irq_restore(flag);
            return result == FLASH_OK;
        }
        irq_restore(flag);
        if ((int32_t)(stop - now) <= 0) {
            window->deferred = window->runtime;
            return 0;
        }
    }
}

static int
counter_program(void *context, unsigned offset, uint16_t value)
{
    // PM0075 permits reprogramming a non-erased halfword only to zero.
    if (offset >= M300_FACTORY_COUNTER_SPAN || (offset & 1u)
        || (counter_read(context, offset) != UINT16_MAX && value != 0))
        return 0;
    return counter_mutate(context, offset, value, 0);
}

static int
counter_erase(void *context, unsigned offset)
{
    if (offset != 0 && offset != M300_FACTORY_NVM_SIZE)
        return 0;
    return counter_mutate(context, offset, 0, 1);
}

static const struct m300_counter_io counter_io_template = {
    .read = counter_read,
    .program = counter_program,
    .erase = counter_erase,
    .write_allowed = counter_write_allowed,
};

void
command_m300_factory_query(uint32_t *args)
{
    uint32_t header = *(volatile const uint32_t *)M300_FACTORY_HW_ADDRESS;
    uint8_t raw = *(volatile const uint8_t *)(M300_FACTORY_HW_ADDRESS + 4);
    struct m300_factory_id id = m300_factory_decode(header, raw);
    sendf("m300_factory_state header=%u raw=%c valid=%c revision=%c z_steps=%hu",
          header, raw, id.valid, id.revision, id.z_steps);
}
// Available before configuration and after shutdown; never arms the board.
DECL_COMMAND_FLAGS(command_m300_factory_query, HF_IN_SHUTDOWN,
                   "m300_factory_query");

void
command_m300_factory_info_query(uint32_t *args)
{
    uint32_t minutes = 0;
    uint8_t valid = m300_factory_minutes(
        (const volatile uint8_t *)M300_FACTORY_NVM_A_ADDRESS,
        (const volatile uint8_t *)M300_FACTORY_NVM_B_ADDRESS, &minutes);
    sendf("m300_factory_info serial=%u time_valid=%c print_minutes=%u",
          factory_serial(), valid, minutes);
}
DECL_COMMAND_FLAGS(command_m300_factory_info_query, HF_IN_SHUTDOWN,
                   "m300_factory_info_query");

void
command_m300_factory_counter_query(uint32_t *args)
{
    struct m300_counter_snapshot snapshot;
    m300_counter_inspect(&counter_io_template, &snapshot);
    sendf("m300_factory_counter_state serial=%u state=%c source=%c"
          " print_minutes=%u settings_crc=%u",
          factory_serial(), snapshot.state, snapshot.source, snapshot.minutes,
          snapshot.settings_crc);
}
DECL_COMMAND_FLAGS(command_m300_factory_counter_query, HF_IN_SHUTDOWN,
                   "m300_factory_counter_query");

void
command_m300_factory_counter_query_runtime(uint32_t *args)
{
    struct m300_counter_snapshot snapshot;
    m300_counter_inspect(&counter_io_template, &snapshot);
    sendf("m300_factory_counter_runtime_state token=%u serial=%u state=%c source=%c"
          " print_minutes=%u settings_crc=%u",
          args[0], factory_serial(), snapshot.state, snapshot.source,
          snapshot.minutes, snapshot.settings_crc);
}
DECL_COMMAND_FLAGS(command_m300_factory_counter_query_runtime, HF_IN_SHUTDOWN,
                   "m300_factory_counter_query_runtime token=%u");

static enum m300_counter_result
commit_counter(const uint32_t *args, struct counter_window *window)
{
    uint32_t serial = factory_serial();
    if (!serial || args[0] != serial)
        return M300_COUNTER_CONFLICT;
    struct m300_counter_io io = counter_io_template;
    io.context = window;
    enum m300_counter_result status = m300_counter_commit(&io, args[1], args[2],
                                                          args[3], args[4]);
    return window->deferred && status == M300_COUNTER_IO_ERROR
        ? M300_COUNTER_NOT_QUIESCENT : status;
}

void
command_m300_factory_counter_commit(uint32_t *args)
{
    struct counter_window window = {0};
    enum m300_counter_result status = commit_counter(args, &window);
    sendf("m300_factory_counter_result status=%c", status);
}
DECL_COMMAND(command_m300_factory_counter_commit,
             "m300_factory_counter_commit serial=%u source=%c expected=%u"
             " target=%u settings_crc=%u");

void
command_m300_factory_counter_commit_runtime(uint32_t *args)
{
    uint32_t now = timer_read_time();
    struct counter_window window = {.runtime = 1, .deadline = args[5],
                                    .wait_until = now + timer_from_us(RUNTIME_WAIT_US)};
    enum m300_counter_result status = M300_COUNTER_NOT_QUIESCENT;
    int32_t remaining = (int32_t)(window.deadline - now);
    if (remaining >= (int32_t)timer_from_us(RUNTIME_START_MARGIN_US)
        && remaining <= (int32_t)timer_from_us(RUNTIME_MAX_DEADLINE_US))
        status = commit_counter(args, &window);
    sendf("m300_factory_counter_runtime_result deadline=%u status=%c",
          window.deadline, status);
}
DECL_COMMAND(command_m300_factory_counter_commit_runtime,
             "m300_factory_counter_commit_runtime serial=%u source=%c expected=%u"
             " target=%u settings_crc=%u deadline=%u");
