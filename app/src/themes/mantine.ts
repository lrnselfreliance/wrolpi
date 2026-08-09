import {createTheme, CSSVariablesResolver, MantineColorsTuple} from '@mantine/core';

/*
 * Bridge between Mantine and the WROLPi theme tokens.
 *
 * Mantine components read Mantine's own CSS variables, so rather than styling
 * components one by one we point those variables at our tokens.  A component
 * therefore never branches on the current theme, and a new theme is still just
 * a table of token values.  See tokens.css and ui-design.md.
 */

/**
 * A Mantine palette whose every shade is the same token.
 *
 * Mantine picks a shade per variant (filled uses 6, light uses 1, and so on).
 * We have one value per color, and the flat design has no shade ramp to honor,
 * so every shade resolves to the token and `color="teal"` follows the theme.
 */
const tokenColor = (token: string): MantineColorsTuple =>
    Array(10).fill(`var(--${token})`) as unknown as MantineColorsTuple;

/**
 * The semantic roles.  A component asks for what a color MEANS; the theme decides
 * how that looks.  Registered as Mantine colors too, so `color='danger'` works on any
 * Mantine component the same way `color='red'` does.  See the note in tokens.css --
 * in night and amber these are brightnesses, not hues.
 */
export const roleNames = ['neutral', 'info', 'success', 'warning', 'danger'] as const;

export type RoleName = typeof roleNames[number];

/**
 * The named colors WROLPi uses, each mapping to a token of the same name.
 *
 * A hue, unlike a role: this is the palette a user picks a nav bar or a calculator group
 * from, where the point is telling one thing from another rather than saying how serious
 * it is.  The same twelve as `navColorHexMap` in components/Vars.js.
 */
export const paletteColorNames = [
    'red', 'orange', 'yellow', 'olive', 'green', 'teal', 'blue', 'violet', 'purple', 'pink',
    'brown', 'grey',
] as const;

export type PaletteColorName = typeof paletteColorNames[number];

const paletteColors = Object.fromEntries(
    [...paletteColorNames, ...roleNames].map(name => [name, tokenColor(name)])
);

export const mantineTheme = createTheme({
    // Hard corners everywhere.  The radius variables are zeroed below as well, so a
    // component that hardcodes `radius="md"` cannot reintroduce a rounded corner.
    defaultRadius: 0,
    fontFamily: 'var(--font-body)',
    fontFamilyMonospace: 'var(--font-mono)',
    headings: {fontFamily: 'var(--font-body)', fontWeight: '600'},
    // Text drawn on filled buttons.  Mantine reads `white` for that, and our tokens
    // already define the correct value per theme (white in light, near-black in dark).
    white: 'var(--btn-text)',
    black: 'var(--text)',
    primaryColor: 'blue',
    // Every shade is identical, so the shade only decides which variable name is read.
    primaryShade: 6,
    // Mantine cannot compute contrast from a `var()`, so it must not try.
    autoContrast: false,
    colors: {
        ...paletteColors,
        /*
         * Mantine reads `dark` and `gray` shades directly for surfaces, borders, and
         * secondary text — table borders, zebra stripes, input chrome, disabled states.
         * They cannot be flattened (the steps carry meaning) and they cannot be left
         * alone either, or those pixels stay neutral gray, which night mode forbids.
         * So each shade is mapped to the token that plays its role.
         */
        dark: [
            'var(--text)', 'var(--text)',            // 0-1: primary text
            'var(--muted)', 'var(--muted)',          // 2-3: secondary text
            'var(--border)', 'var(--border)',        // 4-5: borders and subtle surfaces
            'var(--panel)',                          // 6: default surface
            'var(--bg)',                             // 7: body
            'var(--head)', 'var(--head)',            // 8-9: recessed surfaces
        ] as unknown as MantineColorsTuple,
        gray: [
            'var(--panel)',                          // 0: lightest surface
            'var(--bg)',                             // 1: page
            'var(--head)', 'var(--head)',            // 2-3: recessed surfaces
            'var(--border)', 'var(--border)',        // 4-5: borders
            'var(--muted)', 'var(--muted)',          // 6-7: secondary text
            'var(--text)', 'var(--text)',            // 8-9: primary text
        ] as unknown as MantineColorsTuple,
    },
});

/**
 * Colors Mantine defines per color scheme.  These MUST go in both `light` and
 * `dark` rather than `variables`: Mantine emits its own values under
 * `[data-mantine-color-scheme=...]`, which outranks the `:root` block that
 * `variables` becomes.  Put them in `variables` and Mantine's grays win — which
 * in night mode means neutral gray pixels, defeating the whole point of it.
 */
const schemeColors = {
    // Surfaces and text.
    '--mantine-color-body': 'var(--bg)',
    '--mantine-color-text': 'var(--text)',
    '--mantine-color-bright': 'var(--text)',
    '--mantine-color-dimmed': 'var(--muted)',
    '--mantine-color-placeholder': 'var(--muted)',
    '--mantine-color-anchor': 'var(--blue)',
    '--mantine-color-error': 'var(--red)',

    // The "default" variant: inputs, outline buttons, plain surfaces.
    '--mantine-color-default': 'var(--panel)',
    '--mantine-color-default-hover': 'var(--head)',
    '--mantine-color-default-color': 'var(--text)',
    '--mantine-color-default-border': 'var(--border)',

    '--mantine-color-disabled': 'var(--head)',
    '--mantine-color-disabled-color': 'var(--muted)',
    '--mantine-color-disabled-border': 'var(--border)',
};

/** Point Mantine's own variables at our tokens. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
    // Not scheme-specific, so `:root` is enough.
    variables: {
        // Hard corners.
        '--mantine-radius-default': '0',
        '--mantine-radius-xs': '0',
        '--mantine-radius-sm': '0',
        '--mantine-radius-md': '0',
        '--mantine-radius-lg': '0',
        '--mantine-radius-xl': '0',

        // Flat surfaces: elevation is expressed with borders and background steps.
        '--mantine-shadow-xs': 'none',
        '--mantine-shadow-sm': 'none',
        '--mantine-shadow-md': 'none',
        '--mantine-shadow-lg': 'none',
        '--mantine-shadow-xl': 'none',
    },
    light: schemeColors,
    dark: schemeColors,
});
