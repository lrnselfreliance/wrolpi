import React, {useEffect, useRef, useState} from 'react';
import {Link} from 'react-router';

import {getAiCatalog, getChatModes} from '../api';
import {useAiChat} from '../contexts/AiChatContext';
import {InfoMessage} from './Common';
import {Button, Group, Icon, Loader, Text, TextInput} from './ui';

const MODE_LABELS = {help: 'Help', research: 'Research', system: 'System'};
const MODE_DESCRIPTIONS = {
    help: 'Learn how to use WROLPi',
    research: 'Find and summarize library content',
    system: 'Troubleshoot this WROLPi',
};

// Render an assistant message with WROLPi links clickable.  The model only ever returns
// relative links (/videos/123), which the server computed — never external URLs.
export function LinkifiedText({content}) {
    const parts = String(content || '').split(/(\/[a-zA-Z0-9_\-./?=&%#]+)/g);
    return <span style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
        {parts.map((part, i) => part.startsWith('/') && part.length > 1
            ? <Link key={i} to={part}>{part}</Link>
            : part)}
    </span>;
}

function ToolActivity({activity}) {
    if (!activity || !activity.length) {
        return null;
    }
    return <div>
        {activity.map((item, i) => <Text key={i} size='sm' c='dimmed'>
            {item.pending
                ? <Loader size='xs'/>
                : <Icon name={item.success ? 'check' : 'warning circle'}/>}
            {' '}using {String(item.tool || '').replace(/_/g, ' ')}
        </Text>)}
    </div>;
}

export function ChatMessage({message}) {
    if (message.role === 'user') {
        return <div style={{textAlign: 'right', margin: '0.5em 0'}}>
            <span style={{
                display: 'inline-block', padding: '0.5em 0.8em', borderRadius: 8,
                background: 'var(--panel)', maxWidth: '85%', textAlign: 'left',
            }}>{message.content}</span>
        </div>;
    }
    return <div style={{margin: '0.5em 0'}}>
        {message.status && <Text size='sm' c='dimmed'>{message.status}</Text>}
        <ToolActivity activity={message.activity}/>
        {message.content && <LinkifiedText content={message.content}/>}
        {message.streaming && !message.content && !message.activity?.length && <Loader size='xs'/>}
        {message.error && <Text style={{color: 'var(--danger)'}}>{message.error}</Text>}
    </div>;
}

export function AiChat() {
    const {mode, setMode, messages, sending, send, stop, disabledCode} = useAiChat();
    const [modes, setModes] = useState([]);
    const [slowHardware, setSlowHardware] = useState(false);
    const [aiEnabled, setAiEnabled] = useState(null);
    const [input, setInput] = useState('');
    const bottomRef = useRef(null);

    useEffect(() => {
        getChatModes().then(i => i && setModes(i)).catch(console.error);
        getAiCatalog().then(catalog => {
            if (catalog) {
                setSlowHardware(catalog.slow_hardware === true);
                setAiEnabled(Boolean(catalog.enabled && catalog.active_model));
            }
        }).catch(console.error);
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView?.({behavior: 'smooth'});
    }, [messages]);

    const handleSend = async (content) => {
        setInput('');
        await send(content);
    };

    const notReady = aiEnabled === false || disabledCode === 'AI_DISABLED';
    if (notReady) {
        return <InfoMessage>
            The AI assistant is not ready. Download a model and enable it on
            the <Link to='/ai/manage'>Manage</Link> tab.
        </InfoMessage>;
    }

    const suggestions = (modes.find(i => i.name === mode) || {}).suggestions || [];

    return <>
        {slowHardware && <InfoMessage storageName='hint_ai_chat_slow'>
            This hardware runs the assistant slowly — answers can take minutes.
        </InfoMessage>}

        <Group gap='xs'>
            {(modes.length ? modes.map(i => i.name) : Object.keys(MODE_LABELS)).map(name =>
                <Button
                    key={name}
                    size='sm'
                    color={mode === name ? 'violet' : undefined}
                    aria-pressed={mode === name}
                    onClick={() => setMode(name)}
                >
                    {MODE_LABELS[name] || name}
                </Button>)}
            {mode && <Text size='sm' c='dimmed'>{MODE_DESCRIPTIONS[mode]}</Text>}
        </Group>

        {!mode && <Text style={{marginTop: '1em'}}>
            Pick a mode to start: <b>Help</b> teaches WROLPi, <b>Research</b> searches your
            library, <b>System</b> troubleshoots this device.
        </Text>}

        {mode && <>
            <div style={{minHeight: '40vh', margin: '1em 0'}}>
                {messages.length === 0 && <Group gap='xs'>
                    {suggestions.map(suggestion =>
                        <Button key={suggestion} size='xs' onClick={() => handleSend(suggestion)}>
                            {suggestion}
                        </Button>)}
                </Group>}
                {messages.map((message, i) => <ChatMessage key={i} message={message}/>)}
                <div ref={bottomRef}/>
            </div>

            <form onSubmit={e => {
                e.preventDefault();
                if (!sending) {
                    handleSend(input.trim());
                }
            }}>
                <Group gap='xs' wrap='nowrap'>
                    <TextInput
                        style={{flexGrow: 1}}
                        placeholder='Ask the assistant…'
                        value={input}
                        disabled={sending}
                        onChange={e => setInput(e.target.value)}
                        aria-label='Chat message'
                    />
                    {sending
                        ? <Button role='cancel' onClick={stop}>Stop</Button>
                        : <Button type='submit' color='violet' disabled={!input.trim()}>Send</Button>}
                </Group>
            </form>
        </>}
    </>;
}
