import React from 'react';
import {Menu, Modal as MModal, Tooltip as MTooltip} from '@mantine/core';
import {Button} from './Button';

/*
 * Overlays: modals, confirmations, tooltips, menus.
 */

export type ModalProps = React.ComponentProps<typeof MModal>;

export function Modal(props: ModalProps) {
    return <MModal
        centered
        // Flat surfaces: the overlay separates the modal from the page, not a shadow.
        overlayProps={{backgroundOpacity: 0.55, blur: 0}}
        {...props}
    />
}

export interface ConfirmProps {
    open: boolean;
    title?: React.ReactNode;
    children?: React.ReactNode;
    /** Label for the confirming action.  Name the action ("Delete"), not "OK". */
    confirmLabel?: string;
    cancelLabel?: string;
    /** Style the confirming button as destructive. */
    destructive?: boolean;
    loading?: boolean;
    onConfirm?: () => void;
    onCancel?: () => void;
}

export function Confirm({
    open,
    title,
    children,
    confirmLabel = 'OK',
    cancelLabel = 'Cancel',
    destructive,
    loading,
    onConfirm,
    onCancel,
}: ConfirmProps) {
    return <Modal opened={open} onClose={() => onCancel?.()} title={title} size='sm'>
        {children}
        <div style={{display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18}}>
            <Button role='cancel' onClick={onCancel}>{cancelLabel}</Button>
            <Button role={destructive ? 'danger' : 'save'} loading={loading} onClick={onConfirm}>
                {confirmLabel}
            </Button>
        </div>
    </Modal>
}

export type TooltipProps = React.ComponentProps<typeof MTooltip>;

/** Replaces Semantic's Popup. */
export function Tooltip(props: TooltipProps) {
    return <MTooltip withArrow={false} openDelay={200} {...props}/>
}

export {Menu};
