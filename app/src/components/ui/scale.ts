/*
 * The interface scale, for the few places that must express a length in JavaScript.
 *
 * Sizes belong in ui.css, in rem, where `--ui-scale` reaches them (see themes/tokens.css).
 * Two components cannot do that, because the length is a prop rather than a design decision:
 * CardGroup's `minWidth` sets a grid track and Placeholder's `height` sets a skeleton line.
 * Both took a px number from the caller and both divided it by 16 inline, which put the
 * design-time base in two places with nothing tying them together.
 */

/** The px-per-rem the design is written against, and the browser's own default. */
export const REM_BASE = 16;

/**
 * A px length from a call site, as a rem string, so it grows with the interface scale.
 *
 * Callers keep thinking in px deliberately: a number in a prop is a statement about the
 * unscaled design, which is the size the value was chosen at.
 */
export const pxToRem = (px: number): string => `${px / REM_BASE}rem`;
