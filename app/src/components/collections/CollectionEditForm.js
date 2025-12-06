import React from 'react';
import {Button, Form, Grid, Message} from 'semantic-ui-react';
import {Header, Segment} from '../Theme';
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

    return <Segment>
        {title && <Header as="h1">{title}</Header>}
        {wrolModeContent && <WROLModeMessage content={wrolModeContent}/>}

        {/* Display form-level errors */}
        {form.error && <Message error>
            <Message.Header>Error</Message.Header>
            <p>{form.error}</p>
        </Message>}

        <Form onSubmit={handleSubmit} loading={form.loading} autoComplete="off">
            <Grid stackable>
                {children}

                {appliedTagName && <Grid.Row>
                    <Grid.Column>
                        <SingleTag name={appliedTagName}/>
                    </Grid.Column>
                </Grid.Row>}

                <Grid.Row columns={2}>
                    <Grid.Column>
                        {actionButtons}
                        {onCancel && <Button
                            type='button'
                            onClick={onCancel}
                            disabled={form.disabled}
                            className="action-button-spacing"
                        >
                            Cancel
                        </Button>}
                    </Grid.Column>
                    <Grid.Column>
                        <Button
                            type='submit'
                            color='violet'
                            size='big'
                            floated='right'
                            disabled={form.disabled}
                        >
                            Save
                        </Button>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
        </Form>
    </Segment>;
}
