import React from 'react';
import {Button, Header, Message, Panel} from '../ui';
import {TagsContext} from '../../Tags';
import {WROLModeMessage} from '../Common';

/**
 * Reusable form component for editing collections (Domains, Channels, etc).
 *
 * @param {Object} form - Form object from useForm hook
 * @param {Function} onCancel - Optional callback when cancel is clicked
 * @param {Function} onSubmit - Optional custom submit handler (defaults to form.onSubmit)
 * @param {String} title - Page title to display in header
 * @param {String} wrolModeContent - Content to show in WROL mode message (optional)
 * @param {React.ReactNode} actionButtons - Optional additional action buttons to display in the button row
 * @param {String} appliedTagName - Optional tag name to display (similar to ChannelEditPage pattern)
 * @param {React.ReactNode} children - Form fields to render
 */
export function CollectionEditForm({
                                       form,
                                       onCancel,
                                       onSubmit,
                                       title,
                                       wrolModeContent,
                                       actionButtons,
                                       appliedTagName,
                                       children
                                   }) {
    const {SingleTag} = React.useContext(TagsContext);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (onSubmit) {
            onSubmit(e);
        } else {
            form.onSubmit();
        }
    };

    return <Panel>
        {title && <Header as="h1">{title}</Header>}
        {wrolModeContent && <WROLModeMessage content={wrolModeContent}/>}

        {/* Display form-level errors */}
        {form.error && <Message kind='error' title='Error'>
            <p>{form.error}</p>
        </Message>}

        <form onSubmit={handleSubmit} autoComplete="off">
            {/* Every caller passes library components, so this is a plain flex column. */}
            <div
                className='wrolpi-form-rows'
                style={form.loading ? {opacity: 0.6, pointerEvents: 'none'} : undefined}
            >
                {children}

                {appliedTagName && <div><SingleTag name={appliedTagName}/></div>}

                {/*
                  * The shared row.  It was already a flex row at this gap, but it did not wrap, so
                  * the pages that hand it four action buttons ran out of width on a phone -- which
                  * is why each of those buttons, and the Cancel below, carried `margin-top: 1em`.
                  * That margin is what made them sit lower than Save, `vertical-align: middle`
                  * being measured on the margin box.  Wrapping plus a row gap covers the case the
                  * margin was for, in the axis it actually happens in.
                  */}
                <div className='wrolpi-button-row'>
                    {actionButtons}
                    {/*
                      * Cancel and Save travel together, in a row of their own pushed to the end.
                      * `margin-left: auto` was on Save alone, which was right for a row that could
                      * not wrap: now that it can, Save would drop onto a second line by itself,
                      * flush right, with Cancel left behind among the action buttons.
                      */}
                    <div className='wrolpi-button-row' style={{marginInlineStart: 'auto'}}>
                        {onCancel && <Button
                            type='button'
                            role='cancel'
                            onClick={onCancel}
                            disabled={form.disabled}
                        >
                            Cancel
                        </Button>}
                        <Button
                            type='submit'
                            role='save'
                            size='lg'
                            disabled={form.disabled}
                        >
                            Save
                        </Button>
                    </div>
                </div>
            </div>
        </form>
    </Panel>;
}
