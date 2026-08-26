import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';

import {render} from '../test-utils';
import {AiChatProvider} from '../contexts/AiChatContext';
import {parseSSEBlock} from '../sse';
import {AiChat, LinkifiedText} from './AiChat';

jest.mock('../api', () => ({
    getChatModes: jest.fn().mockResolvedValue([
        {name: 'help', suggestions: ['How do I download videos?']},
        {name: 'research', suggestions: ['Find videos about canning']},
        {name: 'system', suggestions: ['Why is my drive full?']},
    ]),
    getAiCatalog: jest.fn().mockResolvedValue({
        enabled: true, active_model: 'test.gguf', slow_hardware: false,
    }),
}));
jest.mock('../sse', () => ({
    ...jest.requireActual('../sse'),
    streamChat: jest.fn(),
}));

const {getAiCatalog, getChatModes} = require('../api');
const {streamChat} = require('../sse');

const renderChat = () => render(<AiChatProvider><AiChat/></AiChatProvider>);

describe('parseSSEBlock', () => {
    it('parses an event and its JSON data', () => {
        expect(parseSSEBlock('event: token\ndata: {"content": "hi"}'))
            .toEqual({event: 'token', data: {content: 'hi'}});
        expect(parseSSEBlock('')).toBeNull();
    });
});

describe('LinkifiedText', () => {
    it('makes relative WROLPi links clickable', () => {
        render(<LinkifiedText content='See /videos/123 for details'/>);
        const link = screen.getByRole('link', {name: '/videos/123'});
        expect(link).toHaveAttribute('href', '/videos/123');
    });
});

describe('AiChat', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        getChatModes.mockResolvedValue([
            {name: 'help', suggestions: ['How do I download videos?']},
            {name: 'research', suggestions: ['Find videos about canning']},
            {name: 'system', suggestions: ['Why is my drive full?']},
        ]);
        getAiCatalog.mockResolvedValue({enabled: true, active_model: 'test.gguf', slow_hardware: false});
    });

    it('starts with the mode picker; picking a mode shows its suggestion chips', async () => {
        renderChat();
        await waitFor(() => expect(screen.getByRole('button', {name: 'Research'})).toBeInTheDocument());
        expect(screen.getByText(/Pick a mode/)).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Research'}));
        await waitFor(() => expect(screen.getByText('Find videos about canning')).toBeInTheDocument());
    });

    it('streams tokens and tool activity into the conversation', async () => {
        streamChat.mockImplementation(async ({mode, messages}, onEvent) => {
            expect(mode).toBe('research');
            expect(messages[messages.length - 1]).toEqual({role: 'user', content: 'find canning'});
            onEvent('tool_call', {tool: 'search_videos', args: {search_str: 'canning'}});
            onEvent('tool_result', {tool: 'search_videos', success: true});
            onEvent('token', {content: 'One video: '});
            onEvent('token', {content: '/videos/123'});
            onEvent('done', {content: 'One video: /videos/123'});
        });

        renderChat();
        await waitFor(() => expect(screen.getByRole('button', {name: 'Research'})).toBeInTheDocument());
        fireEvent.click(screen.getByRole('button', {name: 'Research'}));

        fireEvent.change(screen.getByLabelText('Chat message'), {target: {value: 'find canning'}});
        fireEvent.click(screen.getByText('Send'));

        await waitFor(() => expect(screen.getByText(/using search videos/)).toBeInTheDocument());
        await waitFor(() => expect(screen.getByRole('link', {name: '/videos/123'})).toBeInTheDocument());
        expect(streamChat).toHaveBeenCalledTimes(1);
    });

    it('switching modes clears the conversation', async () => {
        streamChat.mockImplementation(async (_, onEvent) => {
            onEvent('done', {content: 'An answer.'});
        });
        renderChat();
        await waitFor(() => expect(screen.getByRole('button', {name: 'Help'})).toBeInTheDocument());
        fireEvent.click(screen.getByRole('button', {name: 'Help'}));
        fireEvent.change(screen.getByLabelText('Chat message'), {target: {value: 'hello'}});
        fireEvent.click(screen.getByText('Send'));
        await waitFor(() => expect(screen.getByText('An answer.')).toBeInTheDocument());

        fireEvent.click(screen.getByRole('button', {name: 'System'}));
        await waitFor(() => expect(screen.queryByText('An answer.')).not.toBeInTheDocument());
    });

    it('shows an error event without crashing the conversation', async () => {
        streamChat.mockImplementation(async (_, onEvent) => {
            onEvent('error', {message: 'The AI failed to answer.'});
        });
        renderChat();
        await waitFor(() => expect(screen.getByRole('button', {name: 'Help'})).toBeInTheDocument());
        fireEvent.click(screen.getByRole('button', {name: 'Help'}));
        fireEvent.change(screen.getByLabelText('Chat message'), {target: {value: 'hello'}});
        fireEvent.click(screen.getByText('Send'));
        await waitFor(() => expect(screen.getByText('The AI failed to answer.')).toBeInTheDocument());
    });

    it('points at the Manage tab when AI is not enabled', async () => {
        getAiCatalog.mockResolvedValue({enabled: false, active_model: '', slow_hardware: false});
        renderChat();
        await waitFor(() => expect(screen.getByText(/not ready/)).toBeInTheDocument());
        expect(screen.getByRole('link', {name: 'Manage'})).toHaveAttribute('href', '/ai/manage');
    });
});
