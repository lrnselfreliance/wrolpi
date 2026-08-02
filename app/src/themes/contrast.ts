/*
 * WCAG contrast primitives.
 *
 * These live in `themes/` rather than in Common.js because theme code needs them and
 * Common.js is a large module that imports half the component library -- `themes/`
 * importing it is how an import cycle starts, and this app has already paid for one of
 * those (see import-cycles.test.js).  Common.js re-exports `contrastRatio` from here so
 * its existing callers are unaffected.
 */

/** A hex colour as [r, g, b], accepting both `#rrggbb` and the shorthand `#rgb`. */
export function hexToRGBArray(color: string): number[] | undefined {
    let hex = (typeof color === 'string' ? color : '').trim().replace(/^#/, '');
    if (hex.length === 3) {
        // #abc means #aabbcc, not #0a0b0c.
        hex = hex.split('').map(digit => digit + digit).join('');
    }
    if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
        return undefined;
    }
    const rgb: number[] = [];
    for (let i = 0; i <= 2; i++) rgb[i] = parseInt(hex.substr(i * 2, 2), 16);
    return rgb;
}

/**
 * WCAG relative luminance: sRGB channels linearised first, then Rec. 709 weighted.
 *
 * The linearisation is the part that matters.  Weighting the gamma-encoded bytes directly
 * is a rough approximation that misjudges mid-tone blues and purples badly enough to pick
 * the wrong text colour for them.
 */
export function relativeLuminance(color: string | number[]): number {
    const rgb = (typeof color === 'string') ? hexToRGBArray(color) : color;
    if (!rgb) {
        return 0;
    }
    const linear = rgb.map(value => {
        const channel = value / 255;
        return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    });
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2]);
}

/** WCAG contrast ratio between two colours, from 1:1 (identical) to 21:1 (black on white). */
export function contrastRatio(a: string | number[], b: string | number[]): number {
    const luminances = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
    return (luminances[0] + 0.05) / (luminances[1] + 0.05);
}

/**
 * Whichever candidate actually reads best on `background`.
 *
 * Measures every option rather than comparing a brightness figure to a threshold.  A
 * threshold picks the worse of two options for every mid-tone -- which is the whole
 * defect this exists to avoid -- and a mid-tone is exactly what a user picks when they
 * choose a navbar colour.
 *
 * Ties go to the earlier candidate, so a caller can order them by preference.
 */
export function bestForeground(background: string, candidates: string[]): string | undefined {
    let best: string | undefined;
    let bestRatio = -1;
    candidates.filter(Boolean).forEach((candidate) => {
        const ratio = contrastRatio(candidate, background);
        if (ratio > bestRatio) {
            best = candidate;
            bestRatio = ratio;
        }
    });
    return best;
}
