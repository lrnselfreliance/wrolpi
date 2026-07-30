import React from 'react';
import {
    Checkbox as MCheckbox,
    MultiSelect,
    NumberInput,
    Radio,
    Select as MSelect,
    Switch as MSwitch,
    Textarea as MTextarea,
    TextInput as MTextInput,
} from '@mantine/core';

/*
 * Form controls.
 *
 * All of these are Mantine components, deliberately: every one renders its own
 * markup rather than a native control.  Native checkboxes, radios, and select
 * arrows are drawn by the browser in white, which cannot be restyled and would
 * put white pixels on screen in night mode.  Mantine draws SVG we can color
 * from tokens.
 */

// Mantine reads these per-component variables; pointing them at tokens keeps the
// controls correct in all four themes without any per-theme branching.
const checkboxStyles = {
    '--checkbox-color': 'var(--blue)',
    '--checkbox-icon-color': 'var(--btn-text)',
} as React.CSSProperties;

/*
 * `--switch-color` is the *checked* track and comes from the `color` prop, so it is
 * deliberately not set here.  The thumb must be a token: Mantine's default follows
 * `theme.white`, which is our `--btn-text` — near-black on the dark-based themes.
 *
 * The unchecked track is set in ui.css instead of here.  Mantine writes `--switch-bg`
 * onto the track element itself, so a variable on this root would never reach it.
 */
const switchStyles = {
    '--switch-thumb-bg': 'var(--knob)',
    '--switch-disabled-color': 'var(--head)',
} as React.CSSProperties;

export type CheckboxProps = React.ComponentProps<typeof MCheckbox>;

export function Checkbox({style, ...props}: CheckboxProps) {
    return <MCheckbox style={{...checkboxStyles, ...style}} {...props}/>
}

export type ToggleProps = React.ComponentProps<typeof MSwitch>;

/** An on/off switch.  Replaces Semantic's `Radio toggle`. */
export function Toggle({style, className, ...props}: ToggleProps) {
    return <MSwitch
        className={['wrolpi-switch', className].filter(Boolean).join(' ')}
        style={{...switchStyles, ...style}}
        color='blue'
        {...props}
    />
}

export {
    MTextInput as TextInput,
    MTextarea as Textarea,
    MSelect as Select,
    MultiSelect,
    NumberInput,
    Radio,
};
