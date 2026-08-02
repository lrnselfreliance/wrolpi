import React, {forwardRef} from 'react';
import {ActionIcon, ActionIconProps, Button as MButton, ButtonProps as MButtonProps} from '@mantine/core';
import {Icon} from './Icon';

/*
 * Buttons.
 *
 * Roles carry meaning (Semantic UI heritage): blue = primary/download,
 * green = save/confirm, red = destructive, amber = retry/warning, neutral
 * outline = cancel.  Prefer `role` over naming a color, so a theme that remaps
 * a color keeps the meaning.
 */

export type ButtonRole = 'primary' | 'save' | 'retry' | 'danger' | 'cancel';

const roleProps: Record<ButtonRole, {color?: string; variant: string; className?: string}> = {
    primary: {color: 'blue', variant: 'filled'},
    save: {color: 'green', variant: 'filled'},
    retry: {color: 'yellow', variant: 'filled'},
    // Danger resolves differently per theme (filled in light/dark, dashed outline in
    // night).  The branching lives in ui.css, never in a call site.
    danger: {color: 'red', variant: 'filled', className: 'wrolpi-button-danger'},
    cancel: {variant: 'default'},
};

export interface ButtonProps extends Omit<MButtonProps, 'leftSection' | 'rightSection'> {
    role?: ButtonRole;
    /** Semantic icon name or a Tabler component, rendered before the label. */
    icon?: string | React.ComponentType<any>;
    iconAfter?: string | React.ComponentType<any>;
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
    type?: 'button' | 'submit' | 'reset';
    href?: string;
    target?: string;
    component?: any;
}

const renderIcon = (icon?: string | React.ComponentType<any>) => {
    if (!icon) return undefined;
    return typeof icon === 'string' ? <Icon name={icon}/> : <Icon component={icon}/>;
}

/*
 * Semantic's size names, mapped onto Mantine's scale.
 *
 * Unmigrated call sites still pass `size='tiny'`, and Mantine silently ignores a
 * size it does not know — the button renders at the default size and nobody sees
 * a warning.  Translating here keeps those call sites looking right until they
 * migrate, and costs nothing once they have.
 */
const semanticSizes: Record<string, string> = {
    mini: 'xs',
    tiny: 'xs',
    small: 'sm',
    medium: 'md',
    large: 'lg',
    big: 'lg',
    huge: 'xl',
    massive: 'xl',
};

// Generic so it passes each component's own size type straight through; only a
// string that Semantic knew about is rewritten.
export const resolveSize = <T, >(size: T): T =>
    typeof size === 'string' ? ((semanticSizes[size] ?? size) as T) : size;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>((
    {role, icon, iconAfter, className, children, ...props}, ref
) => {
    const fromRole = role ? roleProps[role] : undefined;

    /*
     * An icon with no label is the button's CONTENT, not a leading icon.
     *
     * Mantine gives `leftSection` a `margin-inline-end` to hold it off the label.  With no
     * label that margin is pure offset: the glyph sits about 8px left of the button's centre,
     * which is what the import and save buttons on the Settings config table looked like next
     * to a correctly centred Restore -- Restore is an IconButton, which centres a lone glyph
     * by construction.
     *
     * `React.Children.toArray` drops null, undefined and booleans, which matters because the
     * file browser's footer passes `{label('Delete')}` and that is null whenever the bar is
     * too narrow for words.  Those buttons are icon-only at exactly the widths where the
     * offset is most visible.
     */
    /*
     * Blank text is not a label.  `toArray` drops null, undefined and booleans, but keeps an
     * empty or whitespace-only string, which would leave the icon in `leftSection` with its
     * margin and the glyph off-centre again.  No call site does that today; the predicate
     * should not depend on that staying true.
     *
     * Two limits, both deliberate.  "Icon-only" means exactly one of `icon`/`iconAfter`: a
     * label-less button with both would keep both section margins and stay mis-centred, and
     * there are no such call sites to design for.  And any ELEMENT child counts as a label,
     * including an empty fragment -- `toArray` does not look inside one, so `<></>` is
     * indistinguishable from real content without recursing into fragment props.
     */
    const labelled = React.Children.toArray(children)
        .some(child => typeof child !== 'string' || child.trim().length > 0);
    const soleIcon = !labelled && (icon || iconAfter) && !(icon && iconAfter)
        ? renderIcon(icon || iconAfter)
        : undefined;

    return <MButton
        ref={ref}
        /*
         * An `href` makes this an anchor.  Mantine needs `component='a'` to render one, and
         * without it the href is accepted and silently dropped — the control looks like a
         * link and navigates nowhere.  Semantic used `as='a'` for this, so every migrated
         * call site that carried `href` alone was quietly broken.
         */
        component={props.component ?? (props.href ? 'a' : undefined)}
        // An explicit color/variant still wins, so a call site can deviate when it must.
        color={props.color ?? fromRole?.color}
        variant={props.variant ?? fromRole?.variant}
        className={[fromRole?.className, className].filter(Boolean).join(' ') || undefined}
        leftSection={soleIcon ? undefined : renderIcon(icon)}
        rightSection={soleIcon ? undefined : renderIcon(iconAfter)}
        /*
         * Marks the icon-only case for ui.css, which makes such a button square so it matches
         * an IconButton of the same size.  A Button is as wide as its content plus padding and
         * an ActionIcon is square, so a row mixing the two -- the map's pin actions are edit
         * (Button), add-to-playlist (IconButton) and delete (Button) -- came out 46, 30 and 46
         * wide at the same nominal size.
         */
        data-icon-only={soleIcon ? 'true' : undefined}
        {...props}
        size={resolveSize(props.size)}
    >
        {soleIcon ?? children}
    </MButton>
});
Button.displayName = 'Button';

export interface IconButtonProps extends Omit<ActionIconProps, 'children'> {
    role?: ButtonRole;
    icon: string | React.ComponentType<any>;
    /** Required: an icon-only button has no visible name. */
    label: string;
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
    type?: 'button' | 'submit' | 'reset';
    href?: string;
    target?: string;
    component?: any;
}

/**
 * A square, icon-only button, exactly as tall as a labelled `Button` beside it.
 *
 * The height needs BOTH halves of the fix.  ui.css aligns ActionIcon's size scale with
 * Button's, and this default aligns the starting point: Mantine defaults ActionIcon to `md`
 * where it defaults Button to `sm`, so leaving it alone would trade a 28-vs-36 mismatch for
 * a 42-vs-36 one.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>((
    {role, icon, label, className, size = 'sm', ...props}, ref
) => {
    const fromRole = role ? roleProps[role] : undefined;
    return <ActionIcon
        ref={ref}
        // See Button: an href without `component='a'` renders a non-navigating button.
        component={props.component ?? (props.href ? 'a' : undefined)}
        aria-label={label}
        title={label}
        color={props.color ?? fromRole?.color}
        variant={props.variant ?? fromRole?.variant ?? 'default'}
        className={[fromRole?.className, className].filter(Boolean).join(' ') || undefined}
        {...props}
        size={resolveSize(size)}
    >
        {renderIcon(icon)}
    </ActionIcon>
});
IconButton.displayName = 'IconButton';

export {ButtonGroup} from '@mantine/core';
