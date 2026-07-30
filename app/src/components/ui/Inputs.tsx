import React, {forwardRef, useId} from 'react';
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

export interface PathInputProps
    extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
    label?: React.ReactNode;
    description?: React.ReactNode;
    error?: React.ReactNode;
    /**
     * A fixed, non-editable path the value hangs off — the media directory, say.  It is
     * not part of the value, and typing never changes it.
     */
    prefix: string;
}

/**
 * A path input with a fixed prefix shown to the left of what the user types.
 *
 * The prefix is a *sibling* of the input rather than a section layered inside it, which is
 * the point: Mantine positions `leftSection` absolutely and reserves room for it with
 * `--input-padding-inline-start`, so a call site that gets that width wrong prints the
 * prefix straight through the value.  Passing `leftSectionWidth='auto'` did exactly that
 * — `padding-inline-start: auto` is invalid, so it resolved to zero and every one of these
 * fields rendered its path on top of its own contents.
 *
 * As two boxes in a flex row there is no width to compute and nothing to overlap.  It also
 * sizes itself to any prefix, which matters here: the media directory is `/media/wrolpi`
 * on a Pi and something else entirely under Docker.
 */
export const PathInput = forwardRef<HTMLInputElement, PathInputProps>((
    {prefix, label, description, error, required, disabled, className, id, ...props}, ref
) => {
    const generated = useId();
    const inputId = id ?? `${generated}-input`;
    const prefixId = `${generated}-prefix`;

    return <div className={['wrolpi-path-input', className].filter(Boolean).join(' ')}>
        {label && <label className='wrolpi-path-input-label' htmlFor={inputId}>
            {label}{required && <span aria-hidden='true'> *</span>}
        </label>}
        <div className='wrolpi-path-input-control' data-disabled={disabled ? true : undefined}
             data-error={error ? true : undefined}>
            {/*
              Described rather than hidden: a screen reader should hear which directory the
              typed path is relative to, since that is the whole point of showing it.
            */}
            <span className='wrolpi-path-input-prefix' id={prefixId}>{prefix}</span>
            <input
                ref={ref}
                id={inputId}
                type='text'
                required={required}
                disabled={disabled}
                aria-describedby={prefixId}
                {...props}
            />
        </div>
        {description && <div className='wrolpi-path-input-description'>{description}</div>}
        {error && <div className='wrolpi-path-input-error'>{error}</div>}
    </div>
});
PathInput.displayName = 'PathInput';

export interface ActionInputProps extends React.ComponentProps<typeof MTextInput> {
    /** Button (or buttons) attached to the input's trailing edge. */
    action?: React.ReactNode;
}

/**
 * A text input with a button joined to its right edge.  Replaces Semantic's
 * `<Input action={...}/>`.
 *
 * The two share one outline rather than sitting side by side, so the pair reads
 * as a single control — the input's own right border is dropped and the button
 * supplies the edge.
 */
export const ActionInput = forwardRef<HTMLInputElement, ActionInputProps>((
    {action, className, ...props}, ref
) => {
    // The ref reaches the input, not the wrapper: callers use it to focus or select the
    // field, and a ref to the surrounding div would do neither.
    if (!action) return <MTextInput ref={ref} className={className} {...props}/>
    return <div className={['wrolpi-action-input', className].filter(Boolean).join(' ')}>
        <MTextInput ref={ref} {...props}/>
        {action}
    </div>
});
ActionInput.displayName = 'ActionInput';

export {
    MTextInput as TextInput,
    MTextarea as Textarea,
    MSelect as Select,
    MultiSelect,
    NumberInput,
    Radio,
};
