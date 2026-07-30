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
             * `ui stackable grid` replicates Semantic's own Grid CSS classes (still loaded
             * globally via semantic-ui-offline while other call sites remain unmigrated).
             * Callers of this component (Channels.js, Archive.js, Playlists.js) still pass
             * Semantic <Grid.Row>/<Grid.Column> children -- they have not migrated to the
             * component library yet. This div keeps their layout without importing
             * semantic-ui-react here. Replace with the real `Grid`/`Grid.Col` once every
             * caller has migrated.
             */}
            <div
                className="ui stackable grid"
                style={form.loading ? {opacity: 0.6, pointerEvents: 'none'} : undefined}
            >
                {children}

                {appliedTagName && <div className="row">
                    <div className="column">
                        <SingleTag name={appliedTagName}/>
                    </div>
                </div>}

                <div className="two column row">
                    <div className="column">
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
                    </div>
                    <div className="column">
                        <Button
                            type='submit'
                            role='save'
                            size='lg'
                            style={{float: 'right'}}
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
