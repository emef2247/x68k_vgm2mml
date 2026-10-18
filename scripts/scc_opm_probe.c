/* Authored probe adapter. YM2151 emulation remains an external dependency. */
#include <stdlib.h>
#include "ym2151.h"
int scc_probe(int clock, int rate, int kc, int kf, const int *parts,
              int count, int warmup, int frames, double *output) {
    if (count < 1 || count > 2 || frames < 1 || warmup < 0) return -1;
    struct ym2151 *chip = ym2151_new(clock, rate);
    if (!chip) return -2;
    ym2151_reset_chip(chip);
    for (int ch = 0; ch < count; ++ch) {
        const int *p = parts + ch * 10;
        ym2151_write_reg(chip, 0x20 + ch, 0xc0 | (p[1] << 3) | p[0]);
        ym2151_write_reg(chip, 0x28 + ch, kc);
        ym2151_write_reg(chip, 0x30 + ch, kf);
        for (int op = 0; op < 4; ++op) {
            int slot = ch + op * 8;
            ym2151_write_reg(chip, 0x40 + slot, p[2 + op]);
            ym2151_write_reg(chip, 0x60 + slot, p[6 + op]);
            ym2151_write_reg(chip, 0x80 + slot, 31);
            ym2151_write_reg(chip, 0xa0 + slot, 0);
            ym2151_write_reg(chip, 0xc0 + slot, 0);
            ym2151_write_reg(chip, 0xe0 + slot, 15);
        }
        ym2151_write_reg(chip, 8, 0x78 | ch);
    }
    int total = warmup + frames;
    SAMP *left = calloc(total, sizeof(SAMP)), *right = calloc(total, sizeof(SAMP));
    if (!left || !right) { free(left); free(right); ym2151_shutdown(chip); free(chip); return -3; }
    SAMP *buffers[2] = {left, right};
    ym2151_update_one(chip, buffers, total);
    for (int i = 0; i < frames; ++i) output[i] = left[warmup + i];
    free(left); free(right); ym2151_shutdown(chip); free(chip);
    return 0;
}
