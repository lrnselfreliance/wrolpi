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
            {/*
              Every caller now passes library components rather than Semantic Grid rows, so
              this is a plain flex column instead of the `ui stackable grid` bridge it used
              to be.  That bridge was the last thing in the app depending on Semantic's
              stylesheet.
            */}
            <div
                className='wrolpi-form-rows'
                style={form.loading ? {opacity: 0.6, pointerEvents: 'none'} : undefined}
            >
                {children}

                {appliedTagName && <div><SingleTag name={appliedTagName}/></div>}

                <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
                    {actionButtons}
                    {onCancel && <Button
                        type='button'
                        role='cancel'
                        onClick={onCancel}
                        disabled={form.disabled}
                        className="action-button-spacing"
                    >
                        Cancel
                    </Button>}
                    <Button
                        type='submit'
                        role='save'
                        size='lg'
                        style={{marginLeft: 'auto'}}
                        disabled={form.disabled}
                    >
                        Save
                    </Button>
                </div>
            </div>
        </form>
    </Panel>;
}
