import React, {useEffect, useId, useRef, useState} from 'react';
import {Icon} from './Icon';
import {IconButton} from './Button';
import {Loader} from './Feedback';

/*
 * The search box, with optional grouped suggestions.
 *
 * Grouped search suggestions.  `results` is
 * `{groupKey: {name, results: [{title, description}]}}`, which is the shape four call
 * sites already build from the API.
 *
 * Suggestions are a combobox: the input keeps focus and owns the keyboard, while
 * `aria-activedescendant` points at the highlighted option.  Arrow keys move,
 * Enter takes the highlighted suggestion or submits what was typed, Escape
 * closes the list without clearing the text.
 */

export interface SearchResult {
    /** The value put into the input when chosen.  Also the visible first line. */
    title: string;
    /** Second line, for context: a channel name, a domain. */
    description?: string;

    [key: string]: any;
}

export interface SearchResultGroup {
    /** Group heading. */
    name: string;
    results: SearchResult[];
}

export type SearchResults = Record<string, SearchResultGroup>;

export interface SearchBoxProps {
    value?: string;
    onChange?: (value: string) => void;
    /** Enter, or the search button.  Receives the current text. */
    onSubmit?: (value: string) => void;
    /** Called with the chosen suggestion. */
    onResultSelect?: (result: SearchResult) => void;
    onBlur?: React.FocusEventHandler<HTMLInputElement>;
    results?: SearchResults;
    /**
     * Render one suggestion's contents.  Callers use this to give a kind of result its
     * own presentation — a tag chip rather than a line of text, say.  Falls back to
     * the title and description.
     */
    resultRenderer?: (result: SearchResult) => React.ReactNode;
    /** Suggestions are being fetched; shows a spinner rather than "no results". */
    loading?: boolean;
    placeholder?: string;
    /** Show a button that empties the input. */
    clearable?: boolean;
    /** Force the clear button's disabled state; defaults to "nothing typed". */
    clearDisabled?: boolean | null;
    onClear?: () => void;
    disabled?: boolean;
    required?: boolean;
    inputRef?: React.Ref<HTMLInputElement>;
    /** Accessible name.  Falls back to the placeholder. */
    label?: string;
    className?: string;
    autoFocus?: boolean;
    name?: string;
    /**
     * Set on the input, not the wrapper, so a caller's own `<label htmlFor>` reaches it.
     *
     * SearchBox takes named props rather than spreading a rest object, so an `id` handed
     * to it used to be dropped in silence.  `DestinationForm` passes one and renders a
     * label pointing at it: the download forms' Destination field has therefore had a
     * label associated with nothing at all, which a pointer user never notices and a
     * screen reader user gets nothing from.
     */
    id?: string;
}

/** Flatten the groups into the order they are displayed, for keyboard movement. */
const flatten = (results?: SearchResults): SearchResult[] =>
    Object.values(results ?? {}).flatMap(group => group?.results ?? []);

export function SearchBox({
    value,
    onChange,
    onSubmit,
    onResultSelect,
    onBlur,
    results,
    resultRenderer,
    loading,
    placeholder = 'Search...',
    clearable,
    clearDisabled = null,
    onClear,
    disabled,
    required,
    inputRef,
    label,
    className,
    autoFocus,
    name,
    id,
}: SearchBoxProps) {
    const [open, setOpen] = useState(false);
    const [highlighted, setHighlighted] = useState(-1);
    const containerRef = useRef<HTMLDivElement>(null);
    const listId = useId();

    const text = value ?? '';
    const flat = flatten(results);
    const hasSuggestions = onResultSelect !== undefined || !!results;

    // Close when focus or a click leaves the box entirely.  A blur handler alone would
    // fire before a click on a suggestion registers.
    useEffect(() => {
        if (!open) return;
        const onDocumentClick = (event: MouseEvent) => {
            if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', onDocumentClick);
        return () => document.removeEventListener('mousedown', onDocumentClick);
    }, [open]);

    const choose = (result: SearchResult) => {
        setOpen(false);
        setHighlighted(-1);
        onResultSelect?.(result);
    }

    const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setHighlighted(-1);
        if (hasSuggestions) setOpen(true);
        onChange?.(event.currentTarget.value);
    }

    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            if (!flat.length) return;
            event.preventDefault();
            setOpen(true);
            const step = event.key === 'ArrowDown' ? 1 : -1;
            setHighlighted(current => {
                // Wrap, so holding a key cannot strand the user at either end.
                const next = current + step;
                if (next < 0) return flat.length - 1;
                if (next >= flat.length) return 0;
                return next;
            });
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (open && highlighted >= 0 && flat[highlighted]) {
                choose(flat[highlighted]);
            } else {
                setOpen(false);
                onSubmit?.(text);
            }
        } else if (event.key === 'Escape') {
            // Closes the list; the typed text is left alone.
            if (open) {
                /*
                 * Escape dismisses the suggestions and nothing more.  Without this the
                 * event carries on to whatever contains the box — inside the search modal
                 * that meant one Escape closed the list and the modal together, so a user
                 * correcting a mistyped query lost the whole modal.  A second Escape, with
                 * the list already closed, still closes it.
                 */
                event.stopPropagation();
            }
            setOpen(false);
            setHighlighted(-1);
        }
    }

    const handleClear = () => {
        onChange?.('');
        onSubmit?.('');
        onClear?.();
        setOpen(false);
    }

    let index = -1;

    return <div
        ref={containerRef}
        className={['wrolpi-searchbox', className].filter(Boolean).join(' ')}
    >
        <div className='wrolpi-searchbox-control'>
            <span className='wrolpi-searchbox-icon'><Icon name='search'/></span>
            <input
                ref={inputRef}
                type='text'
                id={id}
                name={name}
                className='wrolpi-searchbox-input'
                placeholder={placeholder}
                aria-label={label ?? placeholder}
                value={text}
                disabled={disabled}
                required={required}
                autoFocus={autoFocus}
                /*
                 * Inside a modal, Mantine's focus trap moves focus itself and overrides the
                 * input's own autoFocus — it honours this attribute instead.  Setting both
                 * means the field is focused whether or not it is inside a modal, which is
                 * what a caller asking for autoFocus means.
                 */
                data-autofocus={autoFocus ? true : undefined}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                // Open on focus when there is something to say — suggestions, or the fact
                // that they are still being fetched.  Not when the list would just read
                // "No results" at a caller that has not searched yet.
                onFocus={() => hasSuggestions && (flat.length > 0 || loading) && setOpen(true)}
                onBlur={onBlur}
                role={hasSuggestions ? 'combobox' : undefined}
                aria-expanded={hasSuggestions ? open : undefined}
                aria-controls={hasSuggestions ? listId : undefined}
                aria-autocomplete={hasSuggestions ? 'list' : undefined}
                aria-activedescendant={open && highlighted >= 0 ? `${listId}-${highlighted}` : undefined}
            />
            {loading && <span className='wrolpi-searchbox-loading'><Loader size='xs'/></span>}
            {clearable && <IconButton
                icon='close'
                label='Clear search'
                className='wrolpi-searchbox-clear'
                onClick={handleClear}
                disabled={clearDisabled !== null ? clearDisabled : !text}
            />}
        </div>

        {open && hasSuggestions && <div className='wrolpi-searchbox-results' id={listId} role='listbox'>
            {loading && !flat.length && <div className='wrolpi-searchbox-empty'>Searching…</div>}
            {!loading && !flat.length && <div className='wrolpi-searchbox-empty'>No results</div>}
            {Object.entries(results ?? {}).map(([key, group]) => {
                if (!group?.results?.length) return null;
                return <div key={key} className='wrolpi-searchbox-group'>
                    <div className='wrolpi-searchbox-group-name'>{group.name}</div>
                    {group.results.map((result, resultIndex) => {
                        index += 1;
                        const optionIndex = index;
                        return <div
                            key={`${key}-${resultIndex}`}
                            id={`${listId}-${optionIndex}`}
                            role='option'
                            aria-selected={optionIndex === highlighted}
                            className={`wrolpi-searchbox-result${
                                optionIndex === highlighted ? ' wrolpi-searchbox-result-active' : ''}`}
                            // mousedown, not click: the input must not blur first.
                            onMouseDown={event => {
                                event.preventDefault();
                                choose(result);
                            }}
                            onMouseEnter={() => setHighlighted(optionIndex)}
                        >
                            {resultRenderer ? resultRenderer(result) : <>
                                <div className='wrolpi-searchbox-result-title'>{result.title}</div>
                                {result.description && <div className='wrolpi-searchbox-result-description'>
                                    {result.description}
                                </div>}
                            </>}
                        </div>
                    })}
                </div>
            })}
        </div>}
    </div>
}
