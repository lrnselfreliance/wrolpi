import React from 'react';
import {Menu, Modal as MModal, Tooltip as MTooltip} from '@mantine/core';
import {Button} from './Button';

/*
 * Overlays: modals, confirmations, tooltips, menus.
 */

/*
 * Modals.
 *
 * Semantic's compound shape (`Modal.Header` / `Modal.Content` / `Modal.Actions`)
 * is kept because 34 call sites are written against it.  The subcomponents are
 * markers: Modal reads them out of its children and places each in the right
 * slot, so the children stay in source order at the call site.
 */

const ModalHeader = ({children}: {children?: React.ReactNode}) => <>{children}</>;
ModalHeader.displayName = 'Modal.Header';

const ModalContent = ({children}: {children?: React.ReactNode; scrolling?: boolean}) => <>{children}</>;
ModalContent.displayName = 'Modal.Content';

const ModalActions = ({children}: {children?: React.ReactNode}) => <>{children}</>;
ModalActions.displayName = 'Modal.Actions';

// Semantic's size names, mapped onto Mantine's scale.
const modalSizes: Record<string, string> = {
    mini: 'xs',
    tiny: 'sm',
    small: 'md',
    large: 'lg',
    fullscreen: '100%',
};

export interface ModalProps extends Omit<React.ComponentProps<typeof MModal>, 'opened' | 'size'> {
    /** Semantic's name for `opened`.  Either works. */
    open?: boolean;
    opened?: boolean;
    /** A title given directly, instead of a `Modal.Header` child. */
    title?: React.ReactNode;
    /** Semantic size name (mini/tiny/small/large/fullscreen) or a Mantine size. */
    size?: string | number;
    /** Accepted and ignored: the close button is always shown. */
    closeIcon?: boolean;
}

function ModalBase({open, opened, size, closeIcon, title, children, ...props}: ModalProps) {
    const slots: Record<string, React.ReactNode[]> = {header: [], actions: [], body: []};
    React.Children.forEach(children, child => {
        const type = React.isValidElement(child) ? child.type : undefined;
        if (type === ModalHeader) slots.header.push((child as React.ReactElement).props.children);
        else if (type === ModalActions) slots.actions.push((child as React.ReactElement).props.children);
        else slots.body.push(child);
    });

    return <MModal
        opened={opened ?? open ?? false}
        centered
        size={typeof size === 'string' ? (modalSizes[size] ?? size) : size}
        title={slots.header.length ? slots.header : title}
        // Flat surfaces: the overlay separates the modal from the page, not a shadow.
        overlayProps={{backgroundOpacity: 0.55, blur: 0}}
        {...props}
    >
        {slots.body}
        {slots.actions.length > 0 && <div className='wrolpi-modal-actions'>{slots.actions}</div>}
    </MModal>
}

export const Modal = Object.assign(ModalBase, {
    Header: ModalHeader,
    Content: ModalContent,
    Actions: ModalActions,
    // Mantine's own names, for new code.
    Body: ModalContent,
});

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
