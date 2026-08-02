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
import {Label, LabelProps} from './Feedback';

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
    const descriptionId = `${generated}-description`;
    const errorId = `${generated}-error`;

    /*
     * Everything that explains the field, in reading order.  Drawing the description and the
     * error on screen does not announce them -- an unreferenced element is invisible to a
     * screen reader, which would leave a user hearing the label and the prefix but never the
     * variables the path accepts, nor the reason a path was just rejected.
     */
    const describedBy = [
        prefixId,
        description ? descriptionId : null,
        error ? errorId : null,
    ].filter(Boolean).join(' ');

    return <div className={['wrolpi-path-input', className].filter(Boolean).join(' ')}>
        {label && <label className='wrolpi-path-input-label' htmlFor={inputId}>
            {label}{required && <span aria-hidden='true'> *</span>}
        </label>}
        <div className='wrolpi-path-input-control' data-disabled={disabled ? true : undefined}
             data-error={error ? true : undefined}>
            {/*
              Described rather than hidden: a screen reader should hear which directory the
              typed path is relative to, since that is the whole point of showing it.

              `title` carries the full path because the prefix truncates when it is long --
              the media directory is whatever the API reports, and a prefix that refused to
              shrink took the entire row and left the input 18px wide.
            */}
            <span className='wrolpi-path-input-prefix' id={prefixId} title={prefix}>{prefix}</span>
            <input
                ref={ref}
                id={inputId}
                type='text'
                required={required}
                disabled={disabled}
                aria-describedby={describedBy}
                aria-invalid={error ? true : undefined}
                {...props}
            />
        </div>
        {description && <div className='wrolpi-path-input-description' id={descriptionId}>
            {description}
        </div>}
        {error && <div className='wrolpi-path-input-error' id={errorId}>{error}</div>}
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

export interface ColoredInputProps
    extends Omit<React.ComponentProps<typeof MTextInput>, 'color' | 'style'> {
    /** Shown as a Label beside the field.  Omit it and this is a plain TextInput. */
    label?: React.ReactNode;
    /*
     * Applied to the ROW, not the field — every call site uses it for width or margins
     * around the pair.  Narrowed from Mantine's own `style`, which is a union that also
     * accepts a function and an array and so cannot be spread into an object literal.
     */
    style?: React.CSSProperties;
    /*
     * A token colour name for the label, and the SAME union Label accepts rather than a
     * loose `string`: the point of the union is that a theme must have a token by that
     * name, and widening it here would let a call site name a colour that resolves to
     * nothing in every theme.
     */
    color?: LabelProps['color'];
    labelPosition?: 'left' | 'right';
    /** Fill the row rather than sizing to content. */
    fluid?: boolean;
}

/**
 * A text field with a Label welded to one side — the calculators' unit markers ("ft", "Ω",
 * "gal"), which is where all ten of them get their shape.
 *
 * It lives here rather than beside the calculators because it used to live in `Apps.js`,
 * the module that ROUTES to the calculators.  Five calculators imported it, so
 * `Calculators.js` -> a calculator -> `Apps.js` -> `Calculators.js` was a cycle around the
 * hub, and `useCalculators` is a `const`: webpack compiles that to a getter that throws
 * rather than returning undefined when read too early.  The dashboard threw on arrival for
 * a whole editing session.  Nothing in `components/ui` imports from `components/`, so a
 * control kept here cannot close a loop like that again.
 */
export function ColoredInput({
    name, value, label, color, labelPosition = 'left', fluid, style, ...props
}: ColoredInputProps) {
    const labelNode = label ? <Label color={color || 'grey'}>{label}</Label> : null;

    return <div style={{
        display: 'flex', alignItems: 'stretch', gap: 6,
        width: fluid ? '100%' : undefined, ...style,
    }}>
        {labelNode && labelPosition === 'left' && labelNode}
        <MTextInput name={name} value={value} style={{flex: fluid ? 1 : undefined}} {...props}/>
        {labelNode && labelPosition !== 'left' && labelNode}
    </div>
}

export {
    MTextInput as TextInput,
    MTextarea as Textarea,
    MSelect as Select,
    MultiSelect,
    NumberInput,
    Radio,
};
