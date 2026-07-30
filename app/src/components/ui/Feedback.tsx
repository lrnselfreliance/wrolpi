import React from 'react';
import {Loader as MLoader, Skeleton} from '@mantine/core';
import {Icon} from './Icon';
import {SemanticColorName} from '../../themes/mantine';

/*
 * Feedback: messages, labels, progress, status text, loaders.
 *
 * These carry the design rules that change form (not just color) between
 * themes, so their markup is ours and their values come from tokens.
 */

// ------------------------------------------------------------------ Messages

export type MessageKind = 'info' | 'success' | 'warning' | 'error';

const messageColors: Record<MessageKind, string> = {
    info: 'var(--blue)',
    success: 'var(--green)',
    warning: 'var(--amber)',
    error: 'var(--red)',
};

export interface MessageProps {
    kind?: MessageKind;
    title?: React.ReactNode;
    children?: React.ReactNode;
    className?: string;
}

export function Message({kind = 'info', title, children, className}: MessageProps) {
    return <div
        // Errors and warnings interrupt; info and success are announced politely.
        role={kind === 'error' ? 'alert' : 'status'}
        className={['wrolpi-message', kind === 'error' ? 'wrolpi-message-error' : '', className]
            .filter(Boolean).join(' ')}
        style={{['--message-color' as string]: messageColors[kind]}}
    >
        {title && <div className='wrolpi-message-title'>{title}</div>}
        {children && <div className='wrolpi-message-body'>{children}</div>}
    </div>
}

// -------------------------------------------------------------------- Labels

export interface LabelProps {
    color?: SemanticColorName | 'black' | 'white';
    icon?: string | React.ComponentType<any>;
    children?: React.ReactNode;
    onClick?: React.MouseEventHandler<HTMLSpanElement>;
    className?: string;
}

/** A tag/chip.  Filled in light and dark; an outline in night, where a filled
 *  patch would be a bright surface. */
export function Label({color = 'grey', icon, children, onClick, className}: LabelProps) {
    return <span
        className={['wrolpi-label', `wrolpi-label-${color}`, className].filter(Boolean).join(' ')}
        style={{['--label-color' as string]: `var(--${color})`, cursor: onClick ? 'pointer' : undefined}}
        onClick={onClick}
    >
        {icon && (typeof icon === 'string' ? <Icon name={icon} size={14}/> : <Icon component={icon} size={14}/>)}
        {children}
    </span>
}

// ------------------------------------------------------------------ Progress

export interface ProgressProps {
    /** 0-100.  Values outside the range are clamped. */
    percent?: number;
    /** Show the percentage inside the bar. */
    showPercent?: boolean;
    color?: SemanticColorName;
    /** Replaces the percentage with arbitrary text (e.g. "2.1 GB / 5.3 GB"). */
    label?: React.ReactNode;
    className?: string;
}

export function Progress({percent = 0, showPercent = true, color = 'blue', label, className}: ProgressProps) {
    const clamped = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0));
    return <div
        className={['wrolpi-progress', className].filter(Boolean).join(' ')}
        role='progressbar'
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
    >
        <div
            className='wrolpi-progress-fill'
            style={{width: `${clamped}%`, ['--progress-color' as string]: `var(--${color})`}}
        />
        {(showPercent || label) && <span className='wrolpi-progress-text'>
            {label ?? `${Math.round(clamped)}%`}
        </span>}
    </div>
}

// -------------------------------------------------------------------- Status

export type StatusKind = 'complete' | 'active' | 'pending' | 'failed';

const statusIcons: Record<StatusKind, string> = {
    complete: 'check',
    active: 'circle notch',
    pending: 'circle',
    failed: 'x',
};

export interface StatusProps {
    kind: StatusKind;
    children?: React.ReactNode;
    /** Hide the leading icon. */
    plain?: boolean;
}

/**
 * Status text.  Encoded by hue in light and dark; night mode has no hue to
 * spend, so brightness carries it (see ui.css).  Callers name the state, never
 * the color.
 */
export function Status({kind, children, plain}: StatusProps) {
    return <span className={`wrolpi-status wrolpi-status-${kind}`}>
        {!plain && <Icon name={statusIcons[kind]} size={14} loading={kind === 'active'}/>}
        {children}
    </span>
}

// ------------------------------------------------------------------- Loaders

export interface LoaderProps {
    size?: number | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
    label?: string;
}

export function Loader({size = 'sm', label}: LoaderProps) {
    return <MLoader size={size} color='var(--blue)' aria-label={label ?? 'Loading'}/>
}

/** Placeholder for content that has not arrived.  Replaces Semantic's Placeholder. */
export function Placeholder({lines = 3, height = 12}: {lines?: number; height?: number}) {
    return <div style={{display: 'flex', flexDirection: 'column', gap: 8}}>
        {Array.from({length: lines}, (_, index) => <Skeleton
            key={index}
            height={height}
            // A ragged last line reads as text rather than a block.
            width={index === lines - 1 ? '60%' : '100%'}
            radius={0}
            animate
        />)}
    </div>
}

export {Skeleton};
