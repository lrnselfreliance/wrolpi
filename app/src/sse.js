// The app's only streaming client.  `apiCall` is JSON-only with a 60-second timeout, which is
// wrong for a chat answer that streams for minutes — so the AI chat uses fetch + a stream
// reader, parsing Server-Sent Events.
import {API_URI} from './components/Vars';

// Parse one SSE block ("event: name\ndata: {...}") into {event, data}.
export function parseSSEBlock(block) {
    let event = null;
    let data = null;
    for (const line of block.split('\n')) {
        if (line.startsWith('event:')) {
            event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
            try {
                data = JSON.parse(line.slice(5).trim());
            } catch (e) {
                data = null;
            }
        }
    }
    return event ? {event, data} : null;
}

/*
 * POST /api/chat and stream its SSE events to `onEvent(event, data)`.
 *
 * Events: status, token, tool_call, tool_result, done, error (see modules/ai/chat.py).
 * Throws on a non-OK response (e.g. AI disabled) with the API's message; abort with `signal`.
 */
export async function streamChat({mode, messages}, onEvent, signal = undefined) {
    const response = await fetch(`${API_URI}/chat/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode, messages}),
        signal,
    });
    if (!response.ok) {
        let message = `Chat failed: HTTP ${response.status}`;
        let code = null;
        try {
            const content = await response.json();
            message = content.summary || content.message || message;
            code = content.code;
        } catch (e) {
            // Not JSON; keep the HTTP message.
        }
        const error = new Error(message);
        error.code = code;
        throw error;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const {done, value} = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, {stream: true});
        let index;
        while ((index = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, index);
            buffer = buffer.slice(index + 2);
            const parsed = parseSSEBlock(block);
            if (parsed) {
                onEvent(parsed.event, parsed.data);
            }
        }
    }
}
