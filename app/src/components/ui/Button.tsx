import React, {forwardRef} from 'react';
import {ActionIcon, ActionIconProps, Button as MButton, ButtonProps as MButtonProps} from '@mantine/core';
import {Icon} from './Icon';

/*
 * Buttons.
 *
 * Roles carry meaning: blue = primary/download, green = save/confirm,
 * red = destructive, amber = retry/warning, neutral outline = cancel.  Prefer
 * `role` over naming a color, so a theme that remaps a color keeps the meaning.
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
    /** An icon name (see Icon.tsx) or a Tabler component, rendered before the label. */
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
 * WROLPi's size names, mapped onto Mantine's scale.
 *
 * Call sites across the app say `size='tiny'` or `size='huge'`, and Mantine silently
 * ignores a size it does not know — the button renders at the default size, with no
 * warning and nothing on screen to say a size was asked for at all.  One table here
 * is cheaper and safer than rewriting the size on several hundred call sites, and it
 * keeps the vocabulary the rest of the app already reads in.
 */
const sizeAliases: Record<string, string> = {
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
// string in the table above is rewritten.
export const resolveSize = <T, >(size: T): T =>
    typeof size === 'string' ? ((sizeAliases[size] ?? size) as T) : size;

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
         * without it the href is accepted and silently dropped, so a call site carrying
         * `href` alone renders a control that looks like a link and navigates nowhere.
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
        /*
         * `default` only when nothing was asked for.
         *
         * Mantine's `default` variant draws itself entirely from `--mantine-color-default*`
         * and never reads `color`, so `<IconButton color='violet'/>` rendered byte-identical
         * to one with no props at all -- eleven call sites were passing a color that could
         * not reach a pixel, two of them the color a user had picked.  `Button` has no such
         * fallback, which is why the same `color='violet'` works there: Mantine fills in
         * `filled` on its own.  Match it, and keep the neutral default for the icon buttons
         * that name no color, which is most of them.
         */
        variant={props.variant ?? fromRole?.variant ?? (props.color ? 'filled' : 'default')}
        className={[fromRole?.className, className].filter(Boolean).join(' ') || undefined}
        {...props}
        size={resolveSize(size)}
    >
        {renderIcon(icon)}
    </ActionIcon>
});
IconButton.displayName = 'IconButton';

export {ButtonGroup} from '@mantine/core';
