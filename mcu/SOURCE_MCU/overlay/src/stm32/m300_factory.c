// M300 factory identity and the bounded, pre-configuration counter writer.
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

// The high-density, 256 KiB F103 uses the two specified 2 KiB Flash pages.
// The next page (0x0803F800) retains the factory ID/serial and is read-only.
#define FLASH_SIZE_WORD 0x1ffff7e0u
#define STM32F103_HIGH_DENSITY_ID 0x414u
#define M300_FLASH_KEY1 0x45670123u
#define M300_FLASH_KEY2 0xcdef89abu
#define FLASH_STATUS_BITS (FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPRTERR)

_Static_assert(M300_FACTORY_NVM_A_ADDRESS + M300_FACTORY_NVM_SIZE
               == M300_FACTORY_NVM_B_ADDRESS, "noncontiguous NVM banks");
_Static_assert(M300_FACTORY_NVM_B_ADDRESS + M300_FACTORY_NVM_SIZE
               == 0x0803f800u, "NVM banks overlap factory identity");

extern int m300_native_config_started(void);
extern int32_t m300_factory_periodic_margin(void);

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
    return m300_factory_write_allowed() && !m300_native_config_started()
        && (*(volatile const uint16_t *)FLASH_SIZE_WORD == 256)
        && ((DBGMCU->IDCODE & 0xfffu) == STM32F103_HIGH_DENSITY_ID);
}

static uint16_t
counter_read(void *context, unsigned offset)
{
    if (offset >= M300_FACTORY_COUNTER_SPAN || (offset & 1u))
        return UINT16_MAX;
    return *(volatile const uint16_t *)(M300_FACTORY_NVM_A_ADDRESS + offset);
}

// PM0075: only SRAM/peripheral accesses can run while the Flash array is
// busy. The caller has verified that motor and heater gates are off.
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
    while (FLASH->SR & FLASH_SR_BSY) {
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
    return status == FLASH_SR_EOP;
}

static int
counter_mutate(unsigned offset, uint16_t value, int erase)
{
    if (!counter_write_allowed(NULL))
        return 0;
    // HSI is the FPEC programming clock even when SYSCLK uses the HSE PLL.
    RCC->CR |= RCC_CR_HSION;
    uint32_t start = timer_read_time();
    while (!(RCC->CR & RCC_CR_HSIRDY))
        if (timer_read_time() - start > timer_from_us(1000))
            return 0;

    // An erase can stall the CPU's normal IRQ vectors for tens of ms.
    // Start just after the native 100 ms periodic tick, leaving room for
    // the documented max erase interval and the software timeout.
    int32_t margin = timer_from_us(erase ? 65000 : 1000);
    uint32_t limit = timer_from_us(100000);
    while (m300_factory_periodic_margin() < margin)
        if (timer_read_time() - start > limit || !counter_write_allowed(NULL))
            return 0;

    irqstatus_t flag = irq_save();
    int ok = 0;
    if (counter_write_allowed(NULL) && !(FLASH->SR & FLASH_SR_BSY)
        && m300_factory_periodic_margin() >= margin) {
        if (FLASH->CR & FLASH_CR_LOCK) {
            FLASH->KEYR = M300_FLASH_KEY1;
            FLASH->KEYR = M300_FLASH_KEY2;
        }
        if (!(FLASH->CR & FLASH_CR_LOCK))
            ok = counter_flash_op(M300_FACTORY_NVM_A_ADDRESS + offset, value,
                                  erase, timer_from_us(erase ? 60000 : 500));
    }
    irq_restore(flag);
    return ok;
}

static int
counter_program(void *context, unsigned offset, uint16_t value)
{
    // PM0075 permits reprogramming a non-erased halfword only to zero.
    if (offset >= M300_FACTORY_COUNTER_SPAN || (offset & 1u)
        || (counter_read(context, offset) != UINT16_MAX && value != 0))
        return 0;
    return counter_mutate(offset, value, 0);
}

static int
counter_erase(void *context, unsigned offset)
{
    if (offset != 0 && offset != M300_FACTORY_NVM_SIZE)
        return 0;
    return counter_mutate(offset, 0, 1);
}

static const struct m300_counter_io counter_io = {
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
    m300_counter_inspect(&counter_io, &snapshot);
    sendf("m300_factory_counter_state serial=%u state=%c source=%c"
          " print_minutes=%u settings_crc=%u",
          factory_serial(), snapshot.state, snapshot.source, snapshot.minutes,
          snapshot.settings_crc);
}
DECL_COMMAND_FLAGS(command_m300_factory_counter_query, HF_IN_SHUTDOWN,
                   "m300_factory_counter_query");

void
command_m300_factory_counter_commit(uint32_t *args)
{
    uint32_t serial = factory_serial();
    enum m300_counter_result status = M300_COUNTER_CONFLICT;
    if (serial && args[0] == serial)
        status = m300_counter_commit(&counter_io, args[1], args[2], args[3],
                                     args[4]);
    sendf("m300_factory_counter_result status=%c", status);
}
DECL_COMMAND(command_m300_factory_counter_commit,
             "m300_factory_counter_commit serial=%u source=%c expected=%u"
             " target=%u settings_crc=%u");
