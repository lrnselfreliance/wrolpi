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

/*
 * Nested modals: which one is on top.
 *
 * Mantine binds a window-level `keydown` listener per open modal, gated only on whether that
 * modal is open -- there is no check for whether it is the one the user is looking at.  Two
 * modals open meant two listeners, so a single Escape closed BOTH: opening the search modal
 * over the dashboard's download modal and pressing Escape once left you on the dashboard.
 * Semantic handled this; the migration lost it.
 *
 * Mantine's own answer is `Modal.Stack` with a `stackId` per modal, which is the only thing
 * that gates `closeOnEscape`.  It is not used here for two reasons: it requires every call
 * site to be rewritten to hoist its modal into a stack, and it sets `__hidden` on everything
 * below the top -- the parent disappears while the child is open.  We want the parent dimmed
 * and still visible behind the child, which is what it did before.
 *
 * So the wrapper keeps the register itself.  A module-level list rather than React context,
 * because the two modals in the bug are not nested in the JSX at all: the search modal is
 * rendered by KeyboardShortcutsProvider near the app root while the download modal is
 * rendered by the dashboard.  They are siblings that happen to be open at once, and no
 * context relates them.  Most recently opened is on top.
 */
let openModalIds: string[] = [];
const modalStackListeners = new Set<() => void>();
const notifyModalStack = () => modalStackListeners.forEach(listener => listener());

/** Mantine's default modal z-index; popovers and tooltips sit at 300. */
const MODAL_Z_INDEX = 200;

/**
 * Where this modal sits in the stack of open ones.
 *
 * Exported for the tests, which need to assert the register empties -- a modal that failed to
 * deregister would leave every later modal believing it was not on top, and nothing would
 * close on Escape at all.
 */
export const openModalCount = () => openModalIds.length;

function useModalStackPosition(opened: boolean): {isTop: boolean; zIndex: number} {
    const id = React.useId();
    const [, rerender] = React.useReducer((count: number) => count + 1, 0);

    React.useEffect(() => {
        modalStackListeners.add(rerender);
        return () => {
            modalStackListeners.delete(rerender);
        };
    }, []);

    React.useEffect(() => {
        if (!opened) return;
        // Re-opening an already-registered modal moves it to the top, which is what a user
        // who clicked its trigger again means.
        openModalIds = [...openModalIds.filter(other => other !== id), id];
        notifyModalStack();
        return () => {
            openModalIds = openModalIds.filter(other => other !== id);
            notifyModalStack();
        };
    }, [opened, id]);

    const depth = openModalIds.indexOf(id);
    return {
        /*
         * Not yet registered -- the first paint of a modal that just opened, before the
         * effect runs.  It is only on top if nothing else is open; claiming top while a
         * parent is registered gives both modals the same z-index for a frame, which is a
         * visible flash of the wrong one in front when a child opens.
         */
        isTop: depth === -1 ? openModalIds.length === 0 : depth === openModalIds.length - 1,
        /*
         * Two per level, so a child's overlay clears its parent's content.  Kept small on
         * purpose: Mantine puts popovers and select dropdowns at 300, and a modal stack that
         * climbed past that would paint over the dropdowns inside itself.
         */
        zIndex: MODAL_Z_INDEX + Math.max(depth, 0) * 2,
    };
}

function ModalBase({
    open, opened, size, closeIcon, title, children,
    /*
     * Pulled out of `props` so the spread below cannot overwrite the stack's decision.
     *
     * These were set BEFORE `{...props}` at first, which meant a call site passing
     * `closeOnEscape` won and re-armed Mantine's window-level Escape listener on a modal
     * that is not on top -- reinstating the exact bug this exists to fix.  Three call sites
     * pass it: CollectionReorganizeModal and BatchReorganizeModal disable Escape while a
     * reorganize is running, and Flasher while it is writing an image.  Conflict resolution
     * opens as a sibling ON TOP of the reorganize modal, so once the reorganize finished and
     * `closeOnEscape` went back to true, one Escape closed both again.
     *
     * They are composed rather than ignored: "only the top modal answers Escape" and "this
     * modal must not be dismissed while it is busy" are both true, and the answer is AND.
     */
    closeOnEscape = true,
    trapFocus = true,
    zIndex,
    ...props
}: ModalProps) {
    const slots: Record<string, React.ReactNode[]> = {header: [], actions: [], body: []};
    React.Children.forEach(children, child => {
        const type = React.isValidElement(child) ? child.type : undefined;
        if (type === ModalHeader) slots.header.push((child as React.ReactElement).props.children);
        else if (type === ModalActions) slots.actions.push((child as React.ReactElement).props.children);
        else slots.body.push(child);
    });

    const isOpen = opened ?? open ?? false;
    const {isTop, zIndex: stackZIndex} = useModalStackPosition(isOpen);

    return <MModal
        opened={isOpen}
        centered
        size={typeof size === 'string' ? (modalSizes[size] ?? size) : size}
        title={slots.header.length ? slots.header : title}
        // Flat surfaces: the overlay separates the modal from the page, not a shadow.
        overlayProps={{backgroundOpacity: 0.55, blur: 0}}
        {...props}
        /*
         * AFTER the spread, deliberately -- see the destructuring above.  Only the modal on
         * top answers the keyboard: without this every open modal has its own window-level
         * Escape listener and one press closes the lot.  Focus goes with it, because two
         * traps fighting over the same Tab is its own bug and the user is working in the top
         * one.  Mantine's own Modal.Stack applies its stack props after the caller's for the
         * same reason.
         */
        closeOnEscape={isTop && closeOnEscape}
        trapFocus={isTop && trapFocus}
        zIndex={zIndex ?? stackZIndex}
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
    /**
     * Same vocabulary as `Modal`, forwarded to it.  Defaults to `tiny`; widen it only when
     * the confirmation shows something other than a question.
     */
    size?: string | number;
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
    size = 'tiny',
    onConfirm,
    onCancel,
}: ConfirmProps) {
    /*
     * `tiny`, not Mantine's raw `sm`.  Same 380px, but the audited vocabulary -- and the
     * guard in ui.test.js exists to keep raw Mantine names out of call sites.
     *
     * Default rather than fixed.  It was fixed, which made every confirmation in the app
     * 380px whatever it held.  Eight of the nine call sites ask a one-line question, and so
     * does every confirmation `useAPIButton` puts behind a `confirmContent` -- around thirty
     * of them, all prose, which is why APIButton does not forward a size.  The ninth is
     * TaggedDeleteConfirmModal, which lists file paths in a two-column table and had no way
     * to say so.  The default stays narrow because a confirmation wider than its question
     * reads as a bigger decision than it is.
     */
    return <Modal opened={open} onClose={() => onCancel?.()} title={title} size={size}>
        {children}
        {/* Its own class rather than `.wrolpi-modal-actions`: a confirmation's buttons sit
            under its question with no hairline, where a Modal's are a separated footer. */}
        <div className='wrolpi-confirm-actions'>
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
