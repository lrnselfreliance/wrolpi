import React from 'react';
import {act, render, screen} from '../test-utils';
import {useSearchSuggestions} from './Search';
import {TagsContext} from '../Tags';
import {tagsContextFixture} from '../test-fixtures';
import {
    searchEstimateFiles, searchEstimateMap, searchEstimateOthers, searchEstimateZims, searchSuggestions,
} from '../api';

// The global search dropdown's groups are built from useSuggestions.  A "Channels: No results" row
// may only appear once the suggestion request has come back empty, never before the user has
// typed, and never while the request is pending.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    searchSuggestions: jest.fn(),
    searchEstimateFiles: jest.fn(),
    searchEstimateMap: jest.fn(),
    searchEstimateOthers: jest.fn(),
    searchEstimateZims: jest.fn(),
}));

const DEBOUNCE = 500;
const pending = () => new Promise(() => {
});

let hook;

function Probe() {
    hook = useSearchSuggestions('', [], false);
    return <pre data-testid='results'>{JSON.stringify(hook.suggestionsResults)}</pre>;
}

const results = () => JSON.parse(screen.getByTestId('results').textContent);

const renderProbe = () => render(<Probe/>, {
    contexts: [[TagsContext, tagsContextFixture({fuzzyMatchTagsByName: () => []})]],
});

beforeEach(() => {
    jest.useFakeTimers();
    searchEstimateFiles.mockReturnValue(pending());
    searchEstimateMap.mockReturnValue(pending());
    searchEstimateOthers.mockReturnValue(pending());
    searchEstimateZims.mockReturnValue(pending());
});

afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
});

test('no Channels group before anything has been searched', () => {
    searchSuggestions.mockReturnValue(pending());
    renderProbe();
    expect(results().channels).toBeUndefined();
});

test('no Channels group while the suggestion request is pending', () => {
    searchSuggestions.mockReturnValue(pending());
    renderProbe();
    act(() => {
        hook.setSearchStr('foo');
    });
    expect(results().channels).toBeUndefined();

    act(() => {
        jest.advanceTimersByTime(DEBOUNCE);
    });
    expect(searchSuggestions).toHaveBeenCalledWith('foo');
    expect(results().channels).toBeUndefined();
    expect(hook.loading).toBe(true);
});

test('a Channels "No results" row once the server said there are none', async () => {
    let resolve;
    searchSuggestions.mockReturnValue(new Promise(res => resolve = res));
    renderProbe();
    act(() => {
        hook.setSearchStr('foo');
    });
    act(() => {
        jest.advanceTimersByTime(DEBOUNCE);
    });
    await act(async () => {
        resolve({channels: [], domains: [], authors: [], subjects: []});
    });
    expect(results().channels.results).toEqual([{title: 'No results'}]);
});

test('Channels rows once the server found some', async () => {
    let resolve;
    searchSuggestions.mockReturnValue(new Promise(res => resolve = res));
    renderProbe();
    act(() => {
        hook.setSearchStr('foo');
    });
    act(() => {
        jest.advanceTimersByTime(DEBOUNCE);
    });
    await act(async () => {
        resolve({channels: [{id: 3, name: 'Food'}], domains: [], authors: [], subjects: []});
    });
    expect(results().channels.results.map(i => i.title)).toEqual(['Food']);
});
