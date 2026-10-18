/* Authored adapter; emu2149 remains an external MIT-licensed dependency. */
#include <stdint.h>
#include "emu2149.h"

int psg_pcm_render(uint32_t clock, uint64_t frames, const uint64_t *times,
                   const uint8_t *registers, const uint8_t *values,
                   uint64_t count, int16_t *stereo) {
    PSG *chip = PSG_new(clock, 44100);
    if (!chip) return -1;
    PSG_setVolumeMode(chip, 2);
    PSG_setQuality(chip, 1);
    PSG_reset(chip);
    uint64_t next = 0;
    for (uint64_t frame = 0; frame < frames; ++frame) {
        while (next < count && times[next] == frame) {
            PSG_writeReg(chip, registers[next], values[next]);
            ++next;
        }
        int16_t value = PSG_calc(chip);
        stereo[frame * 2] = value;
        stereo[frame * 2 + 1] = value;
    }
    /* Preserve writes exactly at EOF too, although they produce no frame. */
    while (next < count && times[next] == frames) {
        PSG_writeReg(chip, registers[next], values[next]);
        ++next;
    }
    PSG_delete(chip);
    return next == count ? 0 : -2;
}
