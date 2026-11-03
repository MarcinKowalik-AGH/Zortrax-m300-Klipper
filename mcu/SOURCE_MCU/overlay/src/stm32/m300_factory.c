// Read the retained stock factory identity, without modifying Flash or GPIO.
// GPL-3.0-or-later.
#include "command.h"
#include "m300_factory.h"

DECL_CONSTANT("M300_FACTORY_ABI", M300_FACTORY_ABI);
DECL_CONSTANT("M300_FACTORY_HW_ADDRESS", M300_FACTORY_HW_ADDRESS);
DECL_CONSTANT("M300_FACTORY_INFO_ABI", M300_FACTORY_INFO_ABI);

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
    uint32_t header = *(volatile const uint32_t *)M300_FACTORY_SERIAL_ADDRESS;
    uint32_t serial = m300_factory_serial(header,
        (const volatile uint8_t *)(M300_FACTORY_SERIAL_ADDRESS + 4));
    uint32_t minutes = 0;
    uint8_t valid = m300_factory_minutes(
        (const volatile uint8_t *)M300_FACTORY_NVM_A_ADDRESS,
        (const volatile uint8_t *)M300_FACTORY_NVM_B_ADDRESS, &minutes);
    sendf("m300_factory_info serial=%u time_valid=%c print_minutes=%u",
          serial, valid, minutes);
}
DECL_COMMAND_FLAGS(command_m300_factory_info_query, HF_IN_SHUTDOWN,
                   "m300_factory_info_query");
