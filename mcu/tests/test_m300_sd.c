// SPDX-License-Identifier: GPL-3.0-or-later
// Native register/card doubles; does not execute STM32 instructions or hardware.
#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint32_t CRL, CRH, IDR, ODR, BSRR; } GPIO_TypeDef;
typedef struct { uint32_t CR1, CR2, SR, DR; } SPI_TypeDef;
typedef struct { uint32_t APB2ENR, APB2RSTR; } RCC_TypeDef;
static GPIO_TypeDef gpio_a;
static SPI_TypeDef spi;
static RCC_TypeDef rcc;
#define GPIOA (&gpio_a)
#define SPI1 (&spi)
#define RCC (&rcc)
#define M300_SD_TEST 1
#define DECL_CONSTANT_STR(...)
#define DECL_CONSTANT(...)
#define DECL_COMMAND(...)
#define DECL_INIT(...)
#define DECL_SHUTDOWN(...)
#define DECL_TASK(...)
#define get_pclock_frequency(...) 72000000u
struct timer { struct timer *next; uint_fast8_t (*func)(struct timer*); uint32_t waketime; };
struct task_wake { uint8_t wake; };
enum { SF_DONE, SF_RESCHEDULE };
static struct timer *registered;
static void sched_add_timer(struct timer *t) { registered = t; }
static void sched_wake_task(struct task_wake *w) { w->wake = 1; }
static uint8_t sched_check_wake(struct task_wake *w) { uint8_t a=w->wake; w->wake=0; return a; }
static uint32_t now;
static uint32_t timer_read_time(void) { return now++; }
static uint32_t timer_from_us(uint32_t n) { return n; }
static uint8_t timer_is_before(uint32_t a,uint32_t b) { return (int32_t)(a-b)<0; }
static uint8_t response_queue[1024], command_bytes[6], rx, card_cid[16], card_csd[16];
static unsigned qread, qwrite, cpos, wire_bytes, max_burst, commands_seen[64];
static unsigned legacy, bad_crc, bad_token, absent, bad_r1, busy_forever;
static uint32_t last_argument;
static uint16_t card_crc(uint16_t v,uint8_t b) {
    v^=(uint16_t)b<<8;
    for(unsigned i=0;i<8;i++)v=(v<<1)^((v&0x8000)?0x1021:0);
    return v;
}
static void enqueue(uint8_t value) { assert(qwrite<sizeof(response_queue)); response_queue[qwrite++]=value; }
static void block_reply(const uint8_t *p,unsigned length) {
    enqueue(0); enqueue(bad_token?0xfd:0xfe); uint16_t c=0;
    for(unsigned i=0;i<length;i++) { enqueue(p[i]); c=card_crc(c,p[i]); }
    if(bad_crc)c^=1;
    enqueue(c>>8); enqueue(c);
}
static void command_reply(void) {
    unsigned command=command_bytes[0]&63;
    commands_seen[command]++;
    last_argument=(uint32_t)command_bytes[1]<<24 | (uint32_t)command_bytes[2]<<16
                  | (uint32_t)command_bytes[3]<<8 | command_bytes[4];
    if(absent)return;
    if(bad_r1) { enqueue(4); return; }
    switch(command) {
    case 0: assert(command_bytes[5]==0x95); enqueue(1); break;
    case 8:
        assert(command_bytes[5]==0x87 && last_argument==0x1aa);
        enqueue(legacy?5:1);
        if(!legacy) { enqueue(0);enqueue(0);enqueue(1);enqueue(0xaa); }
        break;
    case 55: enqueue(1); break;
    case 41: assert(last_argument==(legacy?0:0x40000000)); enqueue(busy_forever?1:0);break;
    case 58: enqueue(0);enqueue(legacy?0x80:0xc0);enqueue(0xff);enqueue(0x80);enqueue(0);break;
    case 16: assert(legacy && last_argument==512);enqueue(0);break;
    case 10: block_reply(card_cid,16);break;
    case 9: block_reply(card_csd,16);break;
    case 17: {
        uint8_t data[512];
        for(unsigned i=0;i<512;i++)data[i]=(i+last_argument)&255;
        block_reply(data,512);break;
    }
    default: assert(!"non-read-only SD command emitted");
    }
}
static void writel(void *address,uint32_t value) {
    assert(address==&GPIOA->BSRR);
    uint32_t old=GPIOA->ODR;
    GPIOA->ODR=(old|(value&65535))&~(value>>16);
    if(!(old&(1u<<4)) && (GPIOA->ODR&(1u<<4))) qread=qwrite=cpos=0;
}
static void writew(void *address,uint16_t value) {
    assert(address==&SPI1->DR);wire_bytes++;rx=0xff;
    if(GPIOA->ODR&(1u<<4))return;
    if(qread<qwrite) { rx=response_queue[qread++]; return; }
    if(cpos || (value&0xc0)==0x40) {
        command_bytes[cpos++]=value;
        if(cpos==6) { qread=qwrite=cpos=0;command_reply(); }
    }
}
static uint16_t readw(void *address) { assert(address==&SPI1->DR);return rx; }
static unsigned done_count, data_count, last_error, last_length, rejections;
static uint32_t last_session,last_token,last_blocks,last_offset;
static uint8_t last_data[512];
static void sendf(const char *fmt,...) {
    va_list a;va_start(a,fmt);
    last_session=va_arg(a,unsigned);last_token=va_arg(a,unsigned);
    if(strstr(fmt,"m300_sd_done")) {
        done_count++;last_error=va_arg(a,unsigned);last_blocks=va_arg(a,unsigned);
    } else { assert(strstr(fmt,"m300_sd_data"));data_count++;last_offset=va_arg(a,unsigned); }
    last_length=va_arg(a,unsigned);const uint8_t *p=va_arg(a,const uint8_t*);
    assert(last_length<=32);memcpy(last_data,p,last_length);
    va_end(a);
}
static jmp_buf jump;
static unsigned expecting;
static void mock_shutdown(const char *message) { (void)message;assert(expecting);rejections++;longjmp(jump,1); }
#define shutdown(msg) mock_shutdown(msg)
#include "../SOURCE_MCU/overlay/src/stm32/m300_sd.c"
#define REJECT(code) do { expecting=1;if(!setjmp(jump)){code;assert(!"expected shutdown");}expecting=0;}while(0)

static void setup(unsigned is_legacy) {
    configured=sd_fault=sd_ready=sd_active=high_capacity=v2=state=phase=0;
    cached_token=block_count=session=request_token=0;sd_wake.wake=0;
    memset(&gpio_a,0,sizeof(gpio_a));memset(&spi,0,sizeof(spi));memset(&rcc,0,sizeof(rcc));
    memset(commands_seen,0,sizeof(commands_seen));
    qread=qwrite=cpos=wire_bytes=max_burst=0;legacy=is_legacy;
    bad_crc=bad_token=absent=bad_r1=busy_forever=0;
    done_count=data_count=last_error=0;now=0;
    memset(card_csd,0,sizeof(card_csd));
    for(unsigned i=0;i<16;i++)card_cid[i]=i+1;
    if(legacy) {card_csd[5]=9;card_csd[7]=255;card_csd[8]=0xc0;}
    else {card_csd[0]=0x40;card_csd[9]=7;}
    SPI1->SR=3;
    m300_sd_init();
    uint32_t cfg[]={1000000};command_m300_sd_config(cfg);
    assert((72000000u>>(((SPI1->CR1>>3)&7)+1))<=400000);
}
static void tick(void) {
    now=registered->waketime;
    assert(registered->func(registered)==SF_RESCHEDULE);
    unsigned before=wire_bytes;m300_sd_task();
    unsigned burst=wire_bytes-before;if(burst>max_burst)max_burst=burst;
    assert(burst<=32);
}
static void run_until_done(void) {
    unsigned n=0;
    while(sd_active && n++<6000)tick();
    assert(!sd_active);
}
static void open_card(void) {
    uint32_t args[]={123,1};command_m300_sd_open(args);run_until_done();
    assert(last_error==0 && last_session==123 && last_token==1);
    assert(last_length==32 && !memcmp(last_data,card_cid,16));
}
int main(void) {
    unsigned cases=0;
    uint16_t golden_crc=0;const char *golden="123456789";
    for(unsigned i=0;i<9;i++)golden_crc=sd_crc16(golden_crc,golden[i]);
    assert(golden_crc==0x31c3);cases++;
    setup(0);assert(GPIOA->ODR&(1u<<4));assert(((GPIOA->CRL>>24)&15)==8);cases++;
    uint32_t cfg[]={1000000};REJECT(command_m300_sd_config(cfg));cases++;
    open_card();assert(high_capacity && block_count==8192 && commands_seen[16]==0);cases++;
    assert(max_burst<=32 && wire_bytes>80);cases++;
    uint32_t read_args[]={123,2,37};command_m300_sd_read(read_args);run_until_done();
    assert(last_error==0 && cached_token==2 && last_argument==37);cases++;
    uint32_t chunk[]={123,3,2,0,32};command_m300_sd_chunk(chunk);
    assert(data_count==1 && last_offset==0 && last_data[0]==37 && last_data[31]==68);cases++;
    chunk[3]=480;command_m300_sd_chunk(chunk);assert(last_data[31]==36);cases++;
    chunk[3]=481;command_m300_sd_chunk(chunk);assert(last_error==SD_RANGE);cases++;
    chunk[3]=0;chunk[4]=33;command_m300_sd_chunk(chunk);assert(last_error==SD_RANGE);cases++;
    chunk[4]=0;command_m300_sd_chunk(chunk);assert(last_error==SD_RANGE);cases++;
    chunk[4]=32;chunk[2]=1;command_m300_sd_chunk(chunk);assert(last_error==SD_SESSION);cases++;
    read_args[2]=8192;command_m300_sd_read(read_args);assert(last_error==SD_RANGE && !sd_active);cases++;
    read_args[0]=124;read_args[2]=0;command_m300_sd_read(read_args);assert(last_error==SD_SESSION);cases++;
    read_args[0]=123;command_m300_sd_read(read_args);command_m300_sd_read(read_args);
    assert(last_error==SD_BUSY);run_until_done();cases++;
    uint32_t close_args[]={123,20};command_m300_sd_close(close_args);
    assert(!sd_ready && !sd_active && !cached_token && (GPIOA->ODR&(1u<<4)));cases++;
    setup(1);open_card();assert(!high_capacity && block_count==4096 && commands_seen[16]==1);cases++;
    read_args[2]=37;command_m300_sd_read(read_args);run_until_done();
    assert(!last_error && last_argument==37*512u);cases++;
    setup(0);bad_crc=1;uint32_t op[]={123,1};command_m300_sd_open(op);run_until_done();
    assert(last_error==SD_CRC && !sd_ready);cases++;
    setup(0);open_card();bad_crc=1;command_m300_sd_read(read_args);run_until_done();
    assert(last_error==SD_CRC && !cached_token);cases++;
    setup(0);bad_token=1;command_m300_sd_open(op);run_until_done();
    assert(last_error==SD_TOKEN);cases++;
    setup(0);absent=1;command_m300_sd_open(op);run_until_done();
    assert(last_error==SD_TIMEOUT && now>=5000000 && now<5002000);cases++;
    setup(0);busy_forever=1;command_m300_sd_open(op);run_until_done();
    assert(last_error==SD_TIMEOUT);cases++;
    setup(0);bad_r1=1;command_m300_sd_open(op);run_until_done();assert(last_error==SD_COMMAND);cases++;
    setup(0);card_csd[0]=0xc0;command_m300_sd_open(op);run_until_done();assert(last_error==SD_CAPACITY);cases++;
    setup(0);SPI1->SR=0;command_m300_sd_open(op);tick();assert(last_error==SD_SPI && !sd_active);cases++;
    setup(0);command_m300_sd_open(op);SPI1->CR1^=1;REJECT(tick());cases++;
    setup(0);command_m300_sd_open(op);m300_sd_shutdown();
    assert(sd_fault && !sd_active && !sd_ready && (GPIOA->ODR&(1u<<4)) && !(SPI1->CR1&(1u<<6)));
    REJECT(command_m300_sd_open(op));cases++;
    printf("PASS M300 private SD: %u scenario groups; %u shutdown refusals; simulated card/register/scheduler, no physical MCU\n",cases,rejections);
    return 0;
}
