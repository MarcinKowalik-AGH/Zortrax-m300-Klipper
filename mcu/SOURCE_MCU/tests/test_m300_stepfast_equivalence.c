// Exact before/after guard equivalence over all GPIO ports, every single bit,
// representative invalid masks, both levels and all ARM/fault/gate/shutdown
// states. Includes the established native GPIO/ADC/guard regression suite.
#define main board_original_main
#include "test_m300_board.c"
#undef main

struct observation {
    uint32_t result;
    unsigned rejected, fault, armed, fans, forced, shutdown;
    GPIO_TypeDef ports[5];
};

static struct observation
observe(unsigned port, uint32_t bit, unsigned level, unsigned state, int optimized)
{
    prepare(3);
    armed = !!(state & 1); fault = !!(state & 2);
    gates = (state >> 2) & 3; shutdown_active = !!(state & 16);
    if (level) ports[port].ODR |= bit; else ports[port].ODR &= ~bit;
    struct observation out = {0};
    unsigned prior = rejection_count;
    expect_reject = 1;
    if (!setjmp(rejected)) {
        if (optimized)
            out.result = m300_toggle_gpio(&ports[port], bit);
        else {
            uint32_t val = !(ports[port].ODR & bit);
            if (port == 4 && (bit == (1u << 13) || bit == (1u << 14))) {
                unsigned mask = bit == (1u << 13) ? 1 : 2;
                val = !(fan_requested & mask);
            }
            out.result = m300_filter_gpio(&ports[port], bit, val);
        }
    }
    expect_reject = 0;
    out.rejected = rejection_count != prior;
    out.fault=fault;out.armed=armed;out.fans=fan_requested;
    out.forced=fan_forced;out.shutdown=shutdown_active;
    memcpy(out.ports,ports,sizeof(ports));
    return out;
}

int main(void)
{
    assert(board_original_main()==0);
    unsigned cases=0;
    const uint32_t extra[]={0,3,0x98,0x10000,0xffffffff};
    for (unsigned port=0;port<5;port++)
        for (unsigned index=0;index<16+ARRAY_SIZE(extra);index++) {
            uint32_t bit=index<16?1u<<index:extra[index-16];
            for (unsigned state=0;state<32;state++)
                for (unsigned level=0;level<2;level++) {
                    struct observation before=observe(port,bit,level,state,0);
                    struct observation after=observe(port,bit,level,state,1);
                    if (memcmp(&before,&after,sizeof(before))) {
                        fprintf(stderr,"equivalence failure port=%u mask=%08x state=%u level=%u\n",port,bit,state,level);
                        return 1;
                    }
                    cases++;
                }
        }
    printf("PASS_STEPFAST_GUARD_EQUIVALENCE cases=%u\n",cases);
    return 0;
}
