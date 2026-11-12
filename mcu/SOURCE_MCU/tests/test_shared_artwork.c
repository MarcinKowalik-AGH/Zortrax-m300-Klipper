// Production OLED scanline renderer with existing isolated MMIO fixture.
// Emits the actual packed frame; never runs on or flashes printer hardware.
#define main panel_regression_main
#include "test_panel.c"
#undef main

int main(int argc, char **argv) {
    assert(argc == 5);
    unsigned reason=(unsigned)strtoul(argv[1],NULL,10);
    unsigned code=(unsigned)strtoul(argv[2],NULL,10);
    unsigned kind=(unsigned)strtoul(argv[3],NULL,10);
    unsigned frame=(unsigned)strtoul(argv[4],NULL,10);
    assert(reason<=3 && code<=255 && kind<=8 && frame<4);
    local_reason=reason;
    memset(&local_error,0,sizeof(local_error));
    local_error.code=code;
    local_error.kind=kind;
    local_animation_frame=frame;
    for(unsigned y=0;y<64;y++) {
        local_render(y);
        assert(fwrite(local_row,1,128,stdout)==128);
    }
    return 0;
}
