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
}

const renderIcon = (icon?: string | React.ComponentType<any>) => {
    if (!icon) return undefined;
    return typeof icon === 'string' ? <Icon name={icon}/> : <Icon component={icon}/>;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>((
    {role, icon, iconAfter, className, ...props}, ref
) => {
    const fromRole = role ? roleProps[role] : undefined;
    return <MButton
        ref={ref}
        // An explicit color/variant still wins, so a call site can deviate when it must.
        color={props.color ?? fromRole?.color}
        variant={props.variant ?? fromRole?.variant}
        className={[fromRole?.className, className].filter(Boolean).join(' ') || undefined}
        leftSection={renderIcon(icon)}
        rightSection={renderIcon(iconAfter)}
        {...props}
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
}

/** A square, icon-only button. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>((
    {role, icon, label, className, ...props}, ref
) => {
    const fromRole = role ? roleProps[role] : undefined;
    return <ActionIcon
        ref={ref}
        aria-label={label}
        title={label}
        color={props.color ?? fromRole?.color}
        variant={props.variant ?? fromRole?.variant ?? 'default'}
        className={[fromRole?.className, className].filter(Boolean).join(' ') || undefined}
        {...props}
    >
        {renderIcon(icon)}
    </ActionIcon>
});
IconButton.displayName = 'IconButton';

export {ButtonGroup} from '@mantine/core';
