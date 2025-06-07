import React from "react";
import _ from "lodash";
import {InfoPopup, RequiredAsterisk, Toggle, validURL, validURLs} from "../components/Common";
import {FormInput, Icon, TextArea} from "../components/Theme";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";


async function asyncNoOp() {
}

export function useForm({
                            fetcher,
                            submitter,
                            defaultFormData,
                            emptyFormData,
                            onSuccess = asyncNoOp,
                            onFailure = asyncNoOp,
                            onDirty = _.noop,
                            clearOnSuccess = false,
                            fetchOnSuccess = false,
                        }) {
    const [formData, setFormData] = React.useState(defaultFormData || {});
    const [disabled, setDisabled] = React.useState(false);
    const [loading, setLoading] = React.useState(false);
    const [ready, setReady] = React.useState(false);
    const [dirty, setDirty] = React.useState(false);

    const [errors, setErrors] = React.useState({});
    const [validators, setValidators] = React.useState({});
    const [validValues, setValidValues] = React.useState({});
    const [requires, setRequires] = React.useState({});

    const memoizedFormData = React.useMemo(() => formData, [formData]);
    const memoizedErrors = React.useMemo(() => errors, [errors]);
    const memoizedValidValues = React.useMemo(() => validValues, [validValues]);
    const memoizedRequires = React.useMemo(() => requires, [requires]);

    if (clearOnSuccess && fetchOnSuccess) {
        console.error('Cannot use both clearOnSuccess and fetchOnSuccess!');
    }

    if (fetchOnSuccess && !fetcher) {
        console.error('Cannot fetchOnSuccess without fetcher!');
    }

    React.useEffect(() => {
        // Form is dirty if it has deviated from the default.
        setDirty(!_.isEqual(defaultFormData, memoizedFormData));

        const errorValues = Object.values(errors).filter(i => !!i);
        if (errorValues.length > 0) {
            console.debug('Form invalid because it has errors');
            setReady(false);
            return
        }
        const invalidValues = Object.values(memoizedValidValues).filter(i => i !== true);
        if (invalidValues.length > 0) {
            console.debug('Form invalid because it failed validators');
            setReady(false);
            return
        }
        const missingValues = Object.keys(memoizedRequires).filter(i => !_.get(formData, i));
        if (missingValues.length > 0) {
            console.debug(`Form invalid because it is missing required value: ${missingValues[0]}`);
            setReady(false);
            return
        }
        setReady(true);
    }, [loading, memoizedFormData, memoizedErrors, memoizedValidValues, memoizedRequires]);

    const localFetch = async () => {
        if (fetcher) {
            const result = await fetcher();
            setFormData(result);
        }
    }

    React.useEffect(() => {
        localFetch();
    }, []);

    React.useEffect(() => {
        if (dirty) {
            onDirty();
        }
    }, [dirty, onDirty]);

    const patchFormData = (newFormData) => {
        newFormData = {...formData, ...newFormData};
        // console.debug('useForm.patchFormData', newFormData);
        setFormData(newFormData);
    };

    const reset = () => {
        setFormData(emptyFormData || defaultFormData);
    }

    const onSubmit = async () => {
        if (!ready) {
            console.error('Refusing to submit form because it is not ready');
            return;
        }

        setDisabled(true);
        setLoading(true);
        setReady(false);
        try {
            await submitter(formData);
            if (fetchOnSuccess && fetcher) {
                const result = await fetcher();
                setFormData(result);
            } else if (clearOnSuccess) {
                reset();
            }
            await onSuccess();
        } finally {
            setLoading(false);
            setDisabled(false);
            await onFailure();
        }
    }

    // Using useCallback with dependencies to ensure the debounce function doesn't change on every render
    const debouncedValidate = React.useCallback(_.debounce((path, value) => {
        const validator = validators[path];
        let error = null;
        if (validator) {
            try {
                error = validator(value);
            } catch (e) {
                console.error(`Failed to validate ${path}`);
            }
        }
        console.debug('useForm.debouncedValidate', path, value, 'error=', error);
        setValidValues(prev => ({...prev, [path]: !error}));
        setErrors(prev => {
            if (error) {
                return {...prev, [path]: error};
            } else {
                const {[path]: _, ...newErrors} = prev;
                return newErrors;
            }
        });
    }, 300), [validators]);

    const handleInputEvent = (e) => {
        if (e) e.preventDefault();
        let {type, value} = e.target;
        let {path} = e.target.dataset;
        path = path || e.target.name;
        if (type === 'number' && !isNaN(value)) {
            value = parseInt(value);
        }
        console.debug('handleInputEvent', 'path=', path, 'type=', type, 'value=', value);

        // Change value in state first, this part happens immediately
        const newFormData = _.set(formData, path.split('.'), value);
        patchFormData(newFormData);

        // Trigger validation after a delay
        debouncedValidate(path, value);

        return value;
    }

    const addValidator = (path, validator) => {
        if (path && !!validator && !(path in validators)) {
            setValidators({...validators, [path]: validator});
        }
    }

    const addRequires = (name) => {
        if (name && !(name in requires)) {
            setRequires({...requires, [name]: false});
        }
    }

    const setValue = (path, newValue) => {
        patchFormData(_.set(formData, path, newValue));
    }

    const getCustomProps = ({name, validator, type = 'text', path, required = false, afterChange}) => {
        // Props for any other elements.

        path = path || name;
        addValidator(path, validator);
        if (required) {
            addRequires(path);
        }
        const value = _.get(formData, path); // Get a path, separated by .'s
        if (value === undefined) {
            patchFormData(_.set(formData, path, type === 'array' ? [] : null));
        }
        // Allow bypass of `handleInputEvent` which only handles an input event.
        const localSetValue = newValue => {
            setValue(path, newValue);
            debouncedValidate(path, newValue);
        }

        // Props for <input/>, etc.
        const inputProps = {
            type,
            disabled,
            value,
            onChange: (newValue) => {
                setValue(path, newValue);
                if (afterChange) {
                    afterChange(newValue);
                }
            },
            'data-path': path,
        }
        // Attributes about the input, but should not be passed as properties.
        const inputAttrs = {
            valid: validValues[path],
            path,
            localSetValue,
        };
        return [inputProps, inputAttrs]
    }

    const getInputProps = ({
                               name,
                               validator,
                               path,
                               required = false,
                               type = 'text',
                               onChange = null,
                               afterChange = null
                           }) => {
        // Props for <input/>
        path = path || name;

        // Use generic validators if no validator is provided.
        if (!validator && type === 'url') {
            validator = validURL;
        }

        const [customProps, inputAttrs] = getCustomProps({name, validator, path, type, required, afterChange});

        const localHandleInputEvent = async (e) => {
            if (e) e.preventDefault();
            const value = handleInputEvent(e);
            if (onChange) {
                await onChange(value);
            }
        }

        // Attributes that should be passed as properties to the input.
        const inputProps = {
            ...customProps,
            name: name,
            onChange: localHandleInputEvent,
            error: errors[path] || null,
            required: required ? null : undefined,
        }
        return [inputProps, inputAttrs]
    }

    const getSelectionProps = ({name, validator, path, type, required = false, afterChange = null}) => {
        // Props for Dropdowns.
        path = path || name;
        const [customProps, inputAttrs] = getCustomProps({name, validator, type, path, required, afterChange});
        customProps.onChange = (e, {value}) => {
            patchFormData(_.set(formData, path, value));
            if (afterChange) {
                afterChange(value);
            }
        };
        return [customProps, inputAttrs]
    }

    return {
        dirty,
        disabled,
        fetcher: localFetch,
        formData,
        getCustomProps,
        getInputProps,
        getSelectionProps,
        handleInputEvent,
        setValue,
        loading,
        onSubmit,
        ready,
        reset,
    }
}

export const commaSeparatedValidator = (value) => {
    if (typeof value !== 'string') {
        return 'Expected a string';
    }
    if (value.endsWith(',')) {
        return 'Cannot end with comma';
    }
    if (value.startsWith(',')) {
        return 'Cannot start with comma';
    }
}

export function InputForm({
                              form,
                              required = false,
                              name,
                              path,
                              type = 'text',
                              validator,
                              placeholder = '',
                              label,
                              helpContent = null,
                              helpPosition = 'top',
                              extraInputProps = {},
                              disabled = false,
                              onChange = null,
                              message = null,
                          }) {
    const [inputProps, inputAttrs] = form.getInputProps({name, path, validator, type, required, onChange});
    inputProps.disabled = disabled || inputProps.disabled;

    let messageElm = null;
    if (message && message.positive) {
        messageElm = <Message {...message} positive/>;
    } else if (message && message.negative) {
        messageElm = <Message {...message}/>;
    } else if (message) {
        messageElm = <Message {...message}/>;
    }

    return <>
        <label htmlFor={`${name}_input`}>
            <b>{label} {required && <RequiredAsterisk/>}</b>
            {helpContent &&
                <InfoPopup
                    content={helpContent}
                    position={helpPosition}
                />
            }
        </label>
        <FormInput
            id={`${name}_input`}
            placeholder={placeholder}
            error={inputProps.error}
        >
            <input {...extraInputProps} {...inputProps}/>
        </FormInput>
        {messageElm}
    </>
}

export function NumberInputForm({
                                    form,
                                    required,
                                    name,
                                    path,
                                    validator,
                                    placeholder = '',
                                    label,
                                    helpContent,
                                    helpPosition,
                                    min = 1,
                                    max = 9999999999,
                                }) {
    // Default to positive number.
    validator = validator || ((value) => {
        value = _.isNumber(value) ? value : parseInt(value);
        if (value < 0) {
            return 'Number must be positive'
        }
    });

    return <InputForm
        form={form}
        required={required}
        name={name}
        path={path}
        type='number'
        validator={validator}
        placeholder={placeholder}
        label={label}
        helpContent={helpContent}
        helpPosition={helpPosition}
        extraInputProps={{min, max}}
    />
}

export function UrlInput({form, required = true, name = 'url', path = 'url', disabled = false}) {
    const validator = (i) => {
        return validURL(i) ? null : 'Invalid URL';
    };

    return <InputForm
        form={form}
        type='url'
        label='URL'
        required={required}
        name={name}
        path={path}
        validator={validator}
        disabled={disabled}
    />
}

export function UrlsTextarea({name = 'urls', required, form}) {
    required = required !== undefined;

    // Memoize input props to prevent recomputation during render
    const [inputProps, inputAttrs] = React.useMemo(() => {

        const validator = (value) => {
            if (!validURLs(value)) {
                return 'Invalid URLs';
            }
        };

        return form.getInputProps({name, validator, required});
    }, [form, name, required]);

    const handleDrop = (e) => {
        if (e) e.preventDefault();
        const droppedUrl = e.dataTransfer.getData('text');
        let urls = (inputProps.value || '').split('\n');
        urls = [...urls, droppedUrl];
        urls = urls.filter(i => !!i).join('\n');
        inputAttrs.setValue(`${urls}\n`);
    };

    const handleKeyDown = (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            form.onSubmit();
        }
    };

    return (
        <FormInput required error={inputProps.error} label="URLs">
            <TextArea
                id="urls_textarea"
                placeholder="Enter one URL per line"
                name="urls"
                onDrop={handleDrop}
                onKeyDown={handleKeyDown}
                {...inputProps}
            />
        </FormInput>
    );
}

export function ToggleForm({form, name, label, path, icon = null, iconSize = 'big', disabled = false}) {
    const [inputProps, inputAttrs] = form.getCustomProps({name, path})

    const iconElm = icon ? <Icon size={iconSize} name={icon}/> : null;
    return <FormInput
        label={label}>
        {iconElm}
        <Toggle
            disabled={disabled || form.disabled}
            name={name}
            checked={inputProps.value}
            onChange={inputProps.onChange}
        />
    </FormInput>
}
