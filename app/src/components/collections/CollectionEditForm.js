import React from 'react';
import {Button, Form, Grid, Message, TextArea} from 'semantic-ui-react';
import {Header, Segment} from '../Theme';
import {TagsSelector, TagsContext} from '../../Tags';
import {WROLModeMessage} from '../Common';
import {DestinationForm} from '../Download';
import {InputForm} from '../../hooks/useForm';

/**
 * Renders a single form field based on field configuration.
 * Extracted outside the component to avoid recreation on every render.
 *
 * @param {Object} field - Field configuration from metadata
 * @param {Object} form - Form object from useForm hook
 * @param {Object} metadata - Backend-provided metadata containing messages
 */
function renderField(field, form, metadata) {
    const disabled = field.depends_on && !form.formData[field.depends_on];

    switch (field.type) {
        case 'directory':
            return <DestinationForm
                form={form}
                label={field.label}
                name={field.key}
                path={field.key}
                required={field.required}
            />;

        case 'text':
            return <InputForm
                form={form}
                label={field.label}
                name={field.key}
                placeholder={field.placeholder}
                required={field.required}
            />;

        case 'textarea':
            const [textareaProps] = form.getCustomProps({name: field.key, path: field.key, required: field.required});
            return <Form.Field>
                <label>
                    {field.label}
                    {field.required && <span className="required-indicator"> *</span>}
                </label>
                <TextArea
                    placeholder={field.placeholder}
                    {...textareaProps}
                    onChange={(e, {value}) => textareaProps.onChange(value)}
                    rows={3}
                />
            </Form.Field>;

        case 'tag':
            const [tagProps] = form.getCustomProps({name: field.key, path: field.key, required: field.required});
            return <Form.Field disabled={disabled}>
                <label>
                    {field.label}
                    {field.required && <span className="required-indicator"> *</span>}
                </label>
                {disabled && <Message info size='small'>
                    {metadata.messages?.no_directory || 'Set a directory to enable tagging'}
                </Message>}
                <TagsSelector
                    selectedTagNames={tagProps.value ? [tagProps.value] : []}
                    onChange={(tagNames) => tagProps.onChange(tagNames[0] || null)}
                    single={true}
                    disabled={disabled || tagProps.disabled}
                />
                {!disabled && tagProps.value && metadata.messages?.tag_will_move && <Message warning size='small'>
                    {metadata.messages.tag_will_move}
                </Message>}
            </Form.Field>;

        default:
            return null;
    }
}

/**
 * Loading skeleton component for the form.
 */
function FormSkeleton({fieldCount = 3}) {
    return (
        <div>
            {Array.from({length: fieldCount}).map((_, i) => (
                <div key={i} className="form-skeleton-field">
                    <div className="form-skeleton-label"/>
                    <div className={i === fieldCount - 1 ? "form-skeleton-textarea" : "form-skeleton-input"}/>
                </div>
            ))}
            <div style={{display: 'flex', justifyContent: 'flex-end', marginTop: '1em'}}>
                <div className="form-skeleton-button"/>
            </div>
        </div>
    );
}

/**
 * Reusable form component for editing collections (Domains, Channels, etc).
 *
 * @param {Object} form - Form object from useForm hook
 * @param {Object} metadata - Backend-provided metadata containing fields configuration
 * @param {Function} onCancel - Optional callback when cancel is clicked
 * @param {String} title - Page title to display in header
 * @param {String} wrolModeContent - Content to show in WROL mode message (optional)
 * @param {React.ReactNode} actionButtons - Optional additional action buttons to display in the button row
 * @param {String} appliedTagName - Optional tag name to display (similar to ChannelEditPage pattern)
 */
export function CollectionEditForm({
    form,
    metadata,
    onCancel,
    title,
    wrolModeContent,
    actionButtons,
    appliedTagName
}) {
    const {SingleTag} = React.useContext(TagsContext);

    if (!metadata) {
        return <Message warning>
            <Message.Header>No metadata available</Message.Header>
        </Message>;
    }

    const handleSubmit = (e) => {
        e.preventDefault();
        form.onSubmit();
    };

    // Show skeleton when loading and no form data yet
    const showSkeleton = form.loading && Object.keys(form.formData).length === 0;

    return <Segment>
        {title && <Header as="h1">{title}</Header>}
        {wrolModeContent && <WROLModeMessage content={wrolModeContent}/>}

        {/* Display form-level errors */}
        {form.error && <Message error>
            <Message.Header>Error</Message.Header>
            <p>{form.error}</p>
        </Message>}

        {showSkeleton ? (
            <FormSkeleton fieldCount={metadata.fields.length}/>
        ) : (
            <Form onSubmit={handleSubmit} loading={form.loading} autoComplete="off">
                <Grid stackable>
                    {metadata.fields.map(field => (
                        <Grid.Row key={field.key}>
                            <Grid.Column>
                                {renderField(field, form, metadata)}
                            </Grid.Column>
                        </Grid.Row>
                    ))}

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
        )}
    </Segment>;
}
