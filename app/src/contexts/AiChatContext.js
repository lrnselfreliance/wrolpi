/*
 * Conversation state for the AI Chat tab.
 *
 * A Context (not props) because the conversation must survive switching between the Chat and
 * Manage tabs, and the chips/mode picker/input are separate components.  Browser-only by
 * design: v1 keeps no server-side chat history.
 *
 * The context itself is exported so tests can wrap components with the real provider instead
 * of mocking the module (see FileWorkerStatusContext.js for why).
 */
import React, {createContext, useContext, useRef, useState} from 'react';

import {streamChat} from '../sse';

export const AiChatContext = createContext(null);

export function AiChatProvider({children}) {
    const [mode, setModeState] = useState(null);
    // [{role: 'user'|'assistant', content, activity: [{tool, success}], error, streaming}]
    const [messages, setMessages] = useState([]);
    const [sending, setSending] = useState(false);
    const [disabledCode, setDisabledCode] = useState(null);
    const abortRef = useRef(null);

    // Switching modes starts a fresh conversation: small contexts cannot carry a Help
    // conversation into Research mode.
    const setMode = (newMode) => {
        stop();
        setModeState(newMode);
        setMessages([]);
    };

    const stop = () => {
        if (abortRef.current) {
            abortRef.current.abort();
            abortRef.current = null;
        }
        setSending(false);
    };

    const updateLast = (updater) => {
        setMessages(previous => {
            const next = [...previous];
            next[next.length - 1] = updater(next[next.length - 1]);
            return next;
        });
    };

    const send = async (content) => {
        if (!content || !mode || sending) {
            return;
        }
        const history = messages
            .filter(i => !i.error && i.content)
            .map(i => ({role: i.role, content: i.content}));
        const userMessage = {role: 'user', content};
        setMessages(previous => [...previous, userMessage,
            {role: 'assistant', content: '', activity: [], streaming: true}]);
        setSending(true);
        setDisabledCode(null);

        const controller = new AbortController();
        abortRef.current = controller;
        try {
            await streamChat({mode, messages: [...history, userMessage]}, (event, data) => {
                if (event === 'token') {
                    updateLast(m => ({...m, content: m.content + (data?.content || '')}));
                } else if (event === 'status') {
                    updateLast(m => ({...m, status: data?.message}));
                } else if (event === 'tool_call') {
                    updateLast(m => ({...m, activity: [...m.activity, {tool: data?.tool, pending: true}]}));
                } else if (event === 'tool_result') {
                    updateLast(m => ({
                        ...m,
                        activity: m.activity.map((a, i) =>
                            i === m.activity.length - 1 ? {...a, pending: false, success: data?.success} : a),
                    }));
                } else if (event === 'done') {
                    updateLast(m => ({...m, content: data?.content ?? m.content, streaming: false, status: null}));
                } else if (event === 'error') {
                    updateLast(m => ({...m, error: data?.message, streaming: false, status: null}));
                }
            }, controller.signal);
            updateLast(m => ({...m, streaming: false}));
        } catch (e) {
            if (e.name === 'AbortError') {
                updateLast(m => ({...m, streaming: false, error: 'Stopped.'}));
            } else {
                if (e.code === 'AI_DISABLED') {
                    setDisabledCode(e.code);
                }
                updateLast(m => ({...m, streaming: false, error: e.message}));
            }
        } finally {
            abortRef.current = null;
            setSending(false);
        }
    };

    const value = {mode, setMode, messages, sending, send, stop, disabledCode};
    return <AiChatContext.Provider value={value}>{children}</AiChatContext.Provider>;
}

export function useAiChat() {
    const context = useContext(AiChatContext);
    if (!context) {
        throw new Error('useAiChat must be used within AiChatProvider');
    }
    return context;
}
