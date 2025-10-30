import React from 'react';
import {Button, Form, Grid, Message, TextArea} from 'semantic-ui-react';
import {Header, Segment} from '../Theme';
import {TagsSelector, TagsContext} from '../../Tags';
import {WROLModeMessage} from '../Common';
import {DestinationForm} from '../Download';
import {InputForm} from '../../hooks/useForm';

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

    const renderField = (field) => {
        const value = form.formData[field.key] || '';
        const disabled = field.depends_on && !form.formData[field.depends_on];

        switch (field.type) {
            case 'text':
                if (field.key === 'directory') {
                    // Use DestinationForm for directory picker
                    return <DestinationForm
                        key={field.key}
                        form={form}
                        label={field.label}
                        name={field.key}
                        path={field.key}
                        required={field.required}
                    />;
                }
                // Use InputForm for regular text fields
                return <InputForm
                    key={field.key}
                    form={form}
                    label={field.label}
                    name={field.key}
                    placeholder={field.placeholder}
                    required={field.required}
                />;

            case 'textarea':
                // Textarea doesn't have a form component, use manual Field
                const [textareaProps] = form.getCustomProps({name: field.key, path: field.key, required: field.required});
                return <Form.Field key={field.key}>
                    <label>{field.label}{field.required && <span style={{color: 'red'}}> *</span>}</label>
                    <TextArea
                        placeholder={field.placeholder}
                        {...textareaProps}
                        onChange={(e, {value}) => textareaProps.onChange(value)}
                        rows={3}
                    />
                </Form.Field>;

            case 'tag':
                // TagsSelector is custom, use manual Field with form props
                const [tagProps] = form.getCustomProps({name: field.key, path: field.key, required: field.required});
                return <Form.Field key={field.key} disabled={disabled}>
                    <label>{field.label}{field.required && <span style={{color: 'red'}}> *</span>}</label>
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
    };

    return <Segment>
        {title && <Header as="h1">{title}</Header>}
        {wrolModeContent && <WROLModeMessage content={wrolModeContent}/>}

        <Form onSubmit={handleSubmit} loading={form.loading} autoComplete="off">
            <Grid stackable columns={2}>
                {metadata.fields.map(field => (
                    <Grid.Row key={field.key}>
                        <Grid.Column width={16}>
                            {renderField(field)}
                        </Grid.Column>
                    </Grid.Row>
                ))}

                {appliedTagName && <Grid.Row>
                    <Grid.Column>
                        <SingleTag name={appliedTagName}/>
                    </Grid.Column>
                </Grid.Row>}

                <Grid.Row>
                    <Grid.Column width={8}>
                        {actionButtons}
                        {onCancel && <Button
                            type='button'
                            onClick={onCancel}
                            disabled={form.disabled}
                            style={{marginTop: '1em'}}
                        >
                            Cancel
                        </Button>}
                    </Grid.Column>
                    <Grid.Column width={8}>
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
