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
    {role, icon, iconAfter, className, ...props}, ref
) => {
    const fromRole = role ? roleProps[role] : undefined;
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
        leftSection={renderIcon(icon)}
        rightSection={renderIcon(iconAfter)}
        {...props}
        size={resolveSize(props.size)}
    />
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

/** A square, icon-only button. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>((
    {role, icon, label, className, ...props}, ref
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
        size={resolveSize(props.size)}
    >
        {renderIcon(icon)}
    </ActionIcon>
});
IconButton.displayName = 'IconButton';

export {ButtonGroup} from '@mantine/core';
