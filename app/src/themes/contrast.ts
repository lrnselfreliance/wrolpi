/*
 * WCAG contrast primitives.
 *
 * These live in `themes/` rather than in Common.js because theme code needs them and
 * Common.js is a large module that imports half the component library -- `themes/`
 * importing it is how an import cycle starts, and this app has already paid for one of
 * those (see import-cycles.test.js).  Common.js re-exports `contrastRatio` from here so
 * its existing callers are unaffected.
 */

/** A hex colour as [r, g, b], accepting `#rgb`, `#rrggbb`, and `#rrggbbaa`. */
export function hexToRGBArray(color: string): number[] | undefined {
    let hex = (typeof color === 'string' ? color : '').trim().replace(/^#/, '');
    if (hex.length === 3 || hex.length === 4) {
        // #abc means #aabbcc, not #0a0b0c.  A fourth digit is alpha; see parseColor.
        hex = hex.split('').map(digit => digit + digit).join('');
    }
    if (!/^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(hex)) {
        return undefined;
    }
    const rgb: number[] = [];
    for (let i = 0; i <= 2; i++) rgb[i] = parseInt(hex.substr(i * 2, 2), 16);
    return rgb;
}

/**
 * Any colour these measurements can actually read, as [r, g, b] — or undefined.
 *
 * Undefined matters as much as the value.  `relativeLuminance` used to return 0 for
 * everything it could not parse, which is indistinguishable from black: a token written as
 * `rgb(90, 79, 168)` measured as pure black, so the "best" foreground was chosen against a
 * colour the theme does not contain, and the wrong one was frozen into the bar's inline
 * style.  A caller that cannot tell "unreadable" from "black" cannot fall back, and the
 * custom YAML themes ahead of us are exactly where a non-hex token will first appear.
 *
 * Alpha is deliberately dropped rather than rejected: WCAG contrast is defined on composited
 * colour, and what a translucent value composites over is not knowable here.  Every token in
 * tokens.css is opaque, so this only arises for a hand-written theme, where measuring the
 * colour itself is a better answer than refusing.
 */
export function parseColor(color: string): number[] | undefined {
    const value = (typeof color === 'string' ? color : '').trim();
    if (!value) return undefined;
    if (value.startsWith('#')) return hexToRGBArray(value);

    // `rgb(90 79 168 / 0.5)` and `rgba(90, 79, 168, 0.5)` are both current syntax.
    const functional = value.match(/^rgba?\(([^)]*)\)$/i);
    if (functional) {
        const parts = functional[1].split(/[\s,/]+/).filter(Boolean).slice(0, 3);
        if (parts.length !== 3) return undefined;
        const channels = parts.map((part) => {
            // A percentage is 0-100 of full scale; a bare number is already 0-255.
            const numeric = parseFloat(part);
            if (Number.isNaN(numeric)) return NaN;
            return part.includes('%') ? (numeric / 100) * 255 : numeric;
        });
        if (channels.some(Number.isNaN)) return undefined;
        return channels.map(channel => Math.min(255, Math.max(0, channel)));
    }

    // A named colour, `hsl()`, `color-mix()`, or an unresolved `var()`.  Not measurable
    // here, and saying so is the point.
    return undefined;
}

/**
 * WCAG relative luminance: sRGB channels linearised first, then Rec. 709 weighted.
 *
 * The linearisation is the part that matters.  Weighting the gamma-encoded bytes directly
 * is a rough approximation that misjudges mid-tone blues and purples badly enough to pick
 * the wrong text colour for them.
 */
export function relativeLuminance(color: string | number[]): number {
    const rgb = (typeof color === 'string') ? parseColor(color) : color;
    if (!rgb) {
        // Zero is black's luminance, so this is a lie -- but the signature has no way to
        // say otherwise, and every caller that needs to distinguish the two asks
        // `isMeasurable` first.
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

/** Whether a colour can be measured at all, as distinct from measuring as black. */
export const isMeasurable = (color: string): boolean => parseColor(color) !== undefined;

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
