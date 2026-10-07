"""Exact MDX duration notation on a 192-tick whole-note clock."""


def duration_spelling(duration):
    if not isinstance(duration, int) or duration <= 0:
        raise ValueError('MDX duration must be a positive integer')
    for dots in range(3):
        numerator = 192 * ((1 << (dots + 1)) - 1)
        denominator = duration * (1 << dots)
        if numerator % denominator == 0:
            value = numerator // denominator
            # MDX also accepts triplet divisors and one/two-tick values;
            # MGSDRV's divisor restrictions do not apply to this target.
            if value in (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192):
                return str(value) + '.' * dots
    return '%' + str(duration)


def timed(name, duration, *, held=False):
    """Use whole-note chunks for long notes, with ties preserving one attack."""
    if not isinstance(duration, int) or duration < 0:
        raise ValueError('MDX duration must be a nonnegative integer')
    pieces = []
    while duration:
        # A note command encodes at most 256 ticks. Whole-note chunks make
        # longer durations readable without asking the compiler to split them.
        count = min(duration, 65535 if name == 'r' else
                    192 if duration > 256 or (duration > 192 and duration_spelling(duration).startswith('%'))
                    else 256)
        duration -= count
        pieces.append(name + duration_spelling(count))
        if name != 'r' and (duration or held):
            pieces.append('&')
    return ' '.join(pieces)
