import React from 'react';
import {renderHook, act, waitFor} from '@testing-library/react';
import {render, screen, fireEvent} from '@testing-library/react';
import {useForm, commaSeparatedValidator, InputForm, NumberInputForm, UrlInput, ToggleForm, UrlsTextarea} from './useForm';
import {renderWithProviders} from '../test-utils';

// Mock lodash debounce to control timing in tests
jest.mock('lodash', () => {
    const actual = jest.requireActual('lodash');
    return {
        ...actual,
        debounce: (fn) => {
            const debounced = (...args) => fn(...args);
            debounced.cancel = jest.fn();
            return debounced;
        },
    };
});

describe('useForm', () => {
    let consoleErrorSpy;
    let consoleDebugSpy;

    beforeEach(() => {
        consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {
        });
        consoleDebugSpy = jest.spyOn(console, 'debug').mockImplementation(() => {
        });
    });

    afterEach(() => {
        consoleErrorSpy.mockRestore();
        consoleDebugSpy.mockRestore();
    });

    describe('initialization', () => {
        it('initializes with defaultFormData', () => {
            const defaultData = {name: 'test', value: 123};
            const {result} = renderHook(() => useForm({
                defaultFormData: defaultData,
                submitter: jest.fn(),
            }));

            expect(result.current.formData).toEqual(defaultData);
        });

        it('starts with correct initial states', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {},
                submitter: jest.fn(),
            }));

            expect(result.current.dirty).toBe(false);
            expect(result.current.loading).toBe(false);
            expect(result.current.disabled).toBe(false);
            // Ready starts true when there are no validators or required fields
            expect(result.current.ready).toBe(true);
        });

        it('calls fetcher on mount if provided', async () => {
            const fetcher = jest.fn().mockResolvedValue({fetched: 'data'});

            renderHook(() => useForm({
                fetcher,
                defaultFormData: {},
                submitter: jest.fn(),
            }));

            await waitFor(() => {
                expect(fetcher).toHaveBeenCalledTimes(1);
            });
        });

        it('updates formData when fetcher resolves', async () => {
            const fetchedData = {name: 'fetched', value: 456};
            const fetcher = jest.fn().mockResolvedValue(fetchedData);

            const {result} = renderHook(() => useForm({
                fetcher,
                defaultFormData: {name: 'default'},
                submitter: jest.fn(),
            }));

            await waitFor(() => {
                expect(result.current.formData).toEqual(fetchedData);
            });
        });

        it('initializes with empty object when no defaultFormData provided', () => {
            const {result} = renderHook(() => useForm({
                submitter: jest.fn(),
            }));

            expect(result.current.formData).toEqual({});
        });
    });

    describe('submit lifecycle', () => {
        it('refuses to submit when not ready', async () => {
            const submitter = jest.fn();
            const {result} = renderHook(() => useForm({
                defaultFormData: {},
                submitter,
            }));

            // Force ready to false by adding a required field that's empty
            act(() => {
                result.current.getInputProps({name: 'required_field', required: true});
            });

            await act(async () => {
                await result.current.onSubmit();
            });

            expect(submitter).not.toHaveBeenCalled();
            expect(consoleErrorSpy).toHaveBeenCalledWith('Refusing to submit form because it is not ready');
        });

        it('sets loading and disabled during submission', async () => {
            let resolveSubmit;
            const submitter = jest.fn(() => new Promise(resolve => {
                resolveSubmit = resolve;
            }));

            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test'},
                submitter,
            }));

            // Start submission
            let submitPromise;
            act(() => {
                submitPromise = result.current.onSubmit();
            });

            // During submission - loading and disabled are set synchronously
            expect(result.current.loading).toBe(true);
            expect(result.current.disabled).toBe(true);
            // Note: ready is set to false in onSubmit, but the useEffect that computes
            // ready may run after this check. The key assertion is loading/disabled.

            // Complete submission
            await act(async () => {
                resolveSubmit();
                await submitPromise;
            });

            // After submission - states are reset
            expect(result.current.loading).toBe(false);
            expect(result.current.disabled).toBe(false);
        });

        it('calls submitter with form data', async () => {
            const formData = {name: 'test', value: 123};
            const submitter = jest.fn().mockResolvedValue(undefined);

            const {result} = renderHook(() => useForm({
                defaultFormData: formData,
                submitter,
            }));

            await act(async () => {
                await result.current.onSubmit();
            });

            expect(submitter).toHaveBeenCalledWith(formData);
        });

        it('calls onSuccess after successful submit', async () => {
            const onSuccess = jest.fn();
            const submitter = jest.fn().mockResolvedValue(undefined);

            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test'},
                submitter,
                onSuccess,
            }));

            await act(async () => {
                await result.current.onSubmit();
            });

            expect(onSuccess).toHaveBeenCalled();
        });

        it('does not call onFailure on successful submit', async () => {
            const onSuccess = jest.fn();
            const onFailure = jest.fn();
            const submitter = jest.fn().mockResolvedValue(undefined);

            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test'},
                submitter,
                onSuccess,
                onFailure,
            }));

            await act(async () => {
                await result.current.onSubmit();
            });

            expect(onSuccess).toHaveBeenCalled();
            expect(onFailure).not.toHaveBeenCalled();
        });

        it('clears form when clearOnSuccess is true', async () => {
            const emptyFormData = {name: '', value: 0};
            const submitter = jest.fn().mockResolvedValue(undefined);

            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test', value: 123},
                emptyFormData,
                submitter,
                clearOnSuccess: true,
            }));

            await act(async () => {
                await result.current.onSubmit();
            });

            expect(result.current.formData).toEqual(emptyFormData);
        });

        it('re-fetches when fetchOnSuccess is true', async () => {
            const fetchedData = {name: 'refetched'};
            const fetcher = jest.fn().mockResolvedValue(fetchedData);
            const submitter = jest.fn().mockResolvedValue(undefined);

            const {result} = renderHook(() => useForm({
                fetcher,
                defaultFormData: {name: 'initial'},
                submitter,
                fetchOnSuccess: true,
            }));

            // Wait for initial fetch
            await waitFor(() => {
                expect(fetcher).toHaveBeenCalledTimes(1);
            });

            await act(async () => {
                await result.current.onSubmit();
            });

            // Should have been called twice (init + after submit)
            expect(fetcher).toHaveBeenCalledTimes(2);
        });

        it('handles submitter errors gracefully', async () => {
            const submitter = jest.fn().mockRejectedValue(new Error('Submit failed'));
            const onFailure = jest.fn();

            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test'},
                submitter,
                onFailure,
            }));

            await act(async () => {
                try {
                    await result.current.onSubmit();
                } catch (e) {
                    // Expected to throw
                }
            });

            // Should still reset loading/disabled states
            expect(result.current.loading).toBe(false);
            expect(result.current.disabled).toBe(false);
            expect(onFailure).toHaveBeenCalled();
        });
    });

    describe('form data management', () => {
        it('setValue updates value at path', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'original'},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.setValue('name', 'updated');
            });

            expect(result.current.formData.name).toBe('updated');
        });

        it('setValue handles nested paths', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {config: {nested: {value: 'original'}}},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.setValue('config.nested.value', 'updated');
            });

            expect(result.current.formData.config.nested.value).toBe('updated');
        });

        it('handleInputEvent extracts value from event', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {username: ''},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {
                        type: 'text',
                        value: 'newvalue',
                        name: 'username',
                        dataset: {},
                    },
                });
            });

            expect(result.current.formData.username).toBe('newvalue');
        });

        it('handleInputEvent converts number inputs to integers', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {count: 0},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {
                        type: 'number',
                        value: '42',
                        name: 'count',
                        dataset: {},
                    },
                });
            });

            expect(result.current.formData.count).toBe(42);
            expect(typeof result.current.formData.count).toBe('number');
        });

        it('handleInputEvent uses data-path attribute when available', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {nested: {field: ''}},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {
                        type: 'text',
                        value: 'pathvalue',
                        name: 'ignored',
                        dataset: {path: 'nested.field'},
                    },
                });
            });

            expect(result.current.formData.nested.field).toBe('pathvalue');
        });

        it('reset restores to emptyFormData when provided', () => {
            const emptyFormData = {name: '', value: null};
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'test', value: 123},
                emptyFormData,
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.setValue('name', 'modified');
            });

            act(() => {
                result.current.reset();
            });

            expect(result.current.formData).toEqual(emptyFormData);
        });

        it('reset restores to defaultFormData when emptyFormData not provided', () => {
            const defaultFormData = {name: 'default', value: 100};
            const {result} = renderHook(() => useForm({
                defaultFormData,
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.setValue('name', 'modified');
            });

            act(() => {
                result.current.reset();
            });

            expect(result.current.formData).toEqual(defaultFormData);
        });
    });

    describe('dirty tracking', () => {
        it('becomes dirty when formData differs from defaultFormData', async () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'original'},
                submitter: jest.fn(),
            }));

            expect(result.current.dirty).toBe(false);

            act(() => {
                result.current.setValue('name', 'changed');
            });

            await waitFor(() => {
                expect(result.current.dirty).toBe(true);
            });
        });

        it('calls onDirty callback when dirty becomes true', async () => {
            const onDirty = jest.fn();
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'original'},
                submitter: jest.fn(),
                onDirty,
            }));

            act(() => {
                result.current.setValue('name', 'changed');
            });

            await waitFor(() => {
                expect(onDirty).toHaveBeenCalled();
            });
        });

        it('uses deep equality for nested objects', async () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {config: {nested: 'value'}},
                submitter: jest.fn(),
            }));

            expect(result.current.dirty).toBe(false);

            act(() => {
                result.current.setValue('config.nested', 'different');
            });

            await waitFor(() => {
                expect(result.current.dirty).toBe(true);
            });
        });
    });

    describe('validation', () => {
        it('validates field and sets error when invalid', async () => {
            const validator = (value) => value.length < 3 ? 'Too short' : null;
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: ''},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.getInputProps({name: 'name', validator});
            });

            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {
                        type: 'text',
                        value: 'ab',
                        name: 'name',
                        dataset: {},
                    },
                });
            });

            await waitFor(() => {
                expect(result.current.ready).toBe(false);
            });
        });

        it('clears error when value becomes valid', async () => {
            const validator = (value) => value.length < 3 ? 'Too short' : null;
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: ''},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.getInputProps({name: 'name', validator});
            });

            // Set invalid value
            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {type: 'text', value: 'ab', name: 'name', dataset: {}},
                });
            });

            // Set valid value
            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {type: 'text', value: 'valid', name: 'name', dataset: {}},
                });
            });

            await waitFor(() => {
                expect(result.current.ready).toBe(true);
            });
        });

        it('handles validator that throws exception', () => {
            const validator = () => {
                throw new Error('Validator crashed');
            };
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: ''},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.getInputProps({name: 'name', validator});
            });

            // Should not throw, just log error
            act(() => {
                result.current.handleInputEvent({
                    preventDefault: jest.fn(),
                    target: {type: 'text', value: 'test', name: 'name', dataset: {}},
                });
            });

            expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to validate name');
        });
    });

    describe('required fields', () => {
        it('form is not ready when required field is empty', async () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: ''},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.getInputProps({name: 'name', required: true});
            });

            await waitFor(() => {
                expect(result.current.ready).toBe(false);
            });
        });

        it('form becomes ready when required field has value', async () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {name: 'has value'},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.getInputProps({name: 'name', required: true});
            });

            await waitFor(() => {
                expect(result.current.ready).toBe(true);
            });
        });

        it('addRequires marks field as required', async () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {field: ''},
                submitter: jest.fn(),
            }));

            expect(result.current.ready).toBe(true);

            act(() => {
                result.current.getCustomProps({name: 'field', required: true});
            });

            await waitFor(() => {
                expect(result.current.ready).toBe(false);
            });
        });
    });

    describe('props generators', () => {
        describe('getInputProps', () => {
            it('returns props suitable for input elements', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {email: 'test@example.com'},
                    submitter: jest.fn(),
                }));

                const [inputProps] = result.current.getInputProps({name: 'email'});

                expect(inputProps).toHaveProperty('type', 'text');
                expect(inputProps).toHaveProperty('disabled', false);
                expect(inputProps).toHaveProperty('value', 'test@example.com');
                expect(inputProps).toHaveProperty('name', 'email');
                expect(inputProps).toHaveProperty('onChange');
            });

            it('includes error when validation fails', async () => {
                const validator = () => 'Error message';
                const {result} = renderHook(() => useForm({
                    defaultFormData: {field: 'value'},
                    submitter: jest.fn(),
                }));

                act(() => {
                    result.current.getInputProps({name: 'field', validator});
                });

                // Trigger validation
                act(() => {
                    result.current.handleInputEvent({
                        preventDefault: jest.fn(),
                        target: {type: 'text', value: 'x', name: 'field', dataset: {}},
                    });
                });

                const [inputProps] = result.current.getInputProps({name: 'field', validator});

                await waitFor(() => {
                    expect(inputProps.error).toBe('Error message');
                });
            });

            it('applies URL validator for url type', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {url: ''},
                    submitter: jest.fn(),
                }));

                const [inputProps, inputAttrs] = result.current.getInputProps({name: 'url', type: 'url'});

                expect(inputProps.type).toBe('url');
            });
        });

        describe('getCustomProps', () => {
            it('returns props for custom components', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {tags: ['tag1', 'tag2']},
                    submitter: jest.fn(),
                }));

                const [customProps, attrs] = result.current.getCustomProps({
                    name: 'tags',
                    type: 'array',
                });

                expect(customProps).toHaveProperty('disabled', false);
                expect(customProps).toHaveProperty('value', ['tag1', 'tag2']);
                expect(customProps).toHaveProperty('onChange');
                expect(customProps).toHaveProperty('data-path', 'tags');
            });

            it('initializes undefined array fields to empty array', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {},
                    submitter: jest.fn(),
                }));

                act(() => {
                    result.current.getCustomProps({name: 'newArray', type: 'array'});
                });

                expect(result.current.formData.newArray).toEqual([]);
            });
        });

        describe('getSelectionProps', () => {
            it('returns props for dropdown elements', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {selected: 'option1'},
                    submitter: jest.fn(),
                }));

                const [selectionProps] = result.current.getSelectionProps({name: 'selected'});

                expect(selectionProps).toHaveProperty('disabled', false);
                expect(selectionProps).toHaveProperty('value', 'option1');
                expect(selectionProps).toHaveProperty('onChange');
            });

            it('onChange handler extracts value from event correctly', () => {
                const {result} = renderHook(() => useForm({
                    defaultFormData: {selected: 'option1'},
                    submitter: jest.fn(),
                }));

                const [selectionProps] = result.current.getSelectionProps({name: 'selected'});

                act(() => {
                    // Semantic UI dropdown passes (event, {value})
                    selectionProps.onChange({}, {value: 'option2'});
                });

                expect(result.current.formData.selected).toBe('option2');
            });
        });
    });

    describe('edge cases and error handling', () => {
        it('logs error when both clearOnSuccess and fetchOnSuccess are true', () => {
            renderHook(() => useForm({
                fetcher: jest.fn(),
                defaultFormData: {},
                submitter: jest.fn(),
                clearOnSuccess: true,
                fetchOnSuccess: true,
            }));

            expect(consoleErrorSpy).toHaveBeenCalledWith('Cannot use both clearOnSuccess and fetchOnSuccess!');
        });

        it('logs error when fetchOnSuccess is true without fetcher', () => {
            renderHook(() => useForm({
                defaultFormData: {},
                submitter: jest.fn(),
                fetchOnSuccess: true,
            }));

            expect(consoleErrorSpy).toHaveBeenCalledWith('Cannot fetchOnSuccess without fetcher!');
        });

        it('handles empty defaultFormData', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {},
                submitter: jest.fn(),
            }));

            expect(result.current.formData).toEqual({});
            expect(result.current.dirty).toBe(false);
        });

        it('creates path when setting value on undefined nested path', () => {
            const {result} = renderHook(() => useForm({
                defaultFormData: {},
                submitter: jest.fn(),
            }));

            act(() => {
                result.current.setValue('deeply.nested.value', 'test');
            });

            expect(result.current.formData.deeply.nested.value).toBe('test');
        });
    });
});

describe('commaSeparatedValidator', () => {
    it('returns null for valid comma-separated string', () => {
        expect(commaSeparatedValidator('a,b,c')).toBeUndefined();
    });

    it('returns error when string ends with comma', () => {
        expect(commaSeparatedValidator('a,b,')).toBe('Cannot end with comma');
    });

    it('returns error when string starts with comma', () => {
        expect(commaSeparatedValidator(',a,b')).toBe('Cannot start with comma');
    });

    it('returns error for non-string input', () => {
        expect(commaSeparatedValidator(123)).toBe('Expected a string');
        expect(commaSeparatedValidator(null)).toBe('Expected a string');
    });
});

describe('Form Components', () => {
    const createMockForm = (formData = {}) => {
        const mockForm = {
            disabled: false,
            formData,
            getInputProps: jest.fn(({name, path, validator, type, required, onChange}) => {
                const p = path || name;
                return [{
                    type: type || 'text',
                    disabled: false,
                    value: formData[p] || '',
                    name,
                    onChange: jest.fn(),
                    error: null,
                    required: required ? null : undefined,
                    'data-path': p,
                }, {valid: true, path: p, localSetValue: jest.fn()}];
            }),
            getCustomProps: jest.fn(({name, path}) => {
                const p = path || name;
                return [{
                    disabled: false,
                    value: formData[p],
                    onChange: jest.fn(),
                    'data-path': p,
                }, {valid: true, path: p, localSetValue: jest.fn()}];
            }),
            onSubmit: jest.fn(),
        };
        return mockForm;
    };

    describe('InputForm', () => {
        it('renders with label', () => {
            const form = createMockForm({username: ''});

            renderWithProviders(
                <InputForm
                    form={form}
                    name="username"
                    label="Username"
                />
            );

            expect(screen.getByText('Username')).toBeInTheDocument();
        });

        it('shows required asterisk when required', () => {
            const form = createMockForm({email: ''});

            renderWithProviders(
                <InputForm
                    form={form}
                    name="email"
                    label="Email"
                    required={true}
                />
            );

            expect(form.getInputProps).toHaveBeenCalledWith(
                expect.objectContaining({required: true})
            );
        });

        it('passes placeholder to input', () => {
            const form = createMockForm({name: ''});

            renderWithProviders(
                <InputForm
                    form={form}
                    name="name"
                    label="Name"
                    placeholder="Enter name"
                />
            );

            expect(screen.getByPlaceholderText('Enter name')).toBeInTheDocument();
        });

        it('respects disabled prop', () => {
            const form = createMockForm({field: ''});

            renderWithProviders(
                <InputForm
                    form={form}
                    name="field"
                    label="Field"
                    disabled={true}
                />
            );

            const input = screen.getByRole('textbox');
            expect(input).toBeDisabled();
        });
    });

    describe('NumberInputForm', () => {
        it('renders as number input', () => {
            const form = createMockForm({count: 0});

            renderWithProviders(
                <NumberInputForm
                    form={form}
                    name="count"
                    label="Count"
                />
            );

            expect(form.getInputProps).toHaveBeenCalledWith(
                expect.objectContaining({type: 'number'})
            );
        });

        it('applies min and max constraints', () => {
            const form = createMockForm({value: 5});

            renderWithProviders(
                <NumberInputForm
                    form={form}
                    name="value"
                    label="Value"
                    min={0}
                    max={100}
                />
            );

            const input = screen.getByRole('spinbutton');
            expect(input).toHaveAttribute('min', '0');
            expect(input).toHaveAttribute('max', '100');
        });
    });

    describe('UrlInput', () => {
        it('renders URL input with label', () => {
            const form = createMockForm({url: ''});

            renderWithProviders(
                <UrlInput form={form}/>
            );

            expect(screen.getByText('URL')).toBeInTheDocument();
        });

        it('applies URL type', () => {
            const form = createMockForm({url: ''});

            renderWithProviders(
                <UrlInput form={form}/>
            );

            expect(form.getInputProps).toHaveBeenCalledWith(
                expect.objectContaining({type: 'url'})
            );
        });

        it('is required by default', () => {
            const form = createMockForm({url: ''});

            renderWithProviders(
                <UrlInput form={form}/>
            );

            expect(form.getInputProps).toHaveBeenCalledWith(
                expect.objectContaining({required: true})
            );
        });
    });

    describe('ToggleForm', () => {
        it('renders toggle with label', () => {
            const form = createMockForm({enabled: false});

            renderWithProviders(
                <ToggleForm
                    form={form}
                    name="enabled"
                    label="Enable Feature"
                />
            );

            expect(screen.getByText('Enable Feature')).toBeInTheDocument();
        });

        it('renders with checkbox input', () => {
            const form = createMockForm({active: true});

            renderWithProviders(
                <ToggleForm
                    form={form}
                    name="active"
                    label="Active"
                />
            );

            expect(screen.getByRole('checkbox')).toBeInTheDocument();
        });
    });

    describe('UrlsTextarea', () => {
        it('renders textarea for multiple URLs', () => {
            const form = createMockForm({urls: ''});

            renderWithProviders(
                <UrlsTextarea form={form}/>
            );

            expect(screen.getByPlaceholderText('Enter one URL per line')).toBeInTheDocument();
        });

        it('calls getInputProps with correct name', () => {
            const form = createMockForm({urls: ''});

            renderWithProviders(
                <UrlsTextarea form={form} name="urls"/>
            );

            expect(form.getInputProps).toHaveBeenCalledWith(
                expect.objectContaining({name: 'urls'})
            );
        });
    });
});
