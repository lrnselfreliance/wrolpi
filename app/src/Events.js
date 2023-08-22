import React, {useEffect} from 'react';
import {useRecurringTimeout} from "./hooks/customHooks";
import {getEvents} from "./api";
import {toast} from "react-semantic-toasts-2";

const apiEventName = 'apiEvent';

function eventToast(title, description, type = 'info', time = 5000, onClick = null) {
    toast({type: type, title: title, description: description, time: time, onClick: onClick});
}

function handleEvents(events) {
    const newestEvents = {};

    events.forEach(e => {
        const {event, message, subject, dt, url} = e;
        document.dispatchEvent(new CustomEvent(apiEventName, {detail: e}));

        console.debug(`Got event: ${event}`);

        if (event === 'directory_refresh') {
            eventToast(
                'Refresh started',
                message,
                'info',
            );
        }

        if (subject && newestEvents[subject] && newestEvents[subject] > dt) {
            console.debug(`Already handled newer event of "${subject}".`);
            return;
        } else if (event === 'refresh_completed') {
            eventToast('Refresh completed', 'Files have been refreshed.', 'success');
        }

        if (event === 'shutdown') {
            eventToast('Shutdown', message, 'warning');
        }

        if (event === 'shutdown_failed') {
            eventToast('Shutdown Failed', message, 'error');
        }

        if (event === 'downloads_disabled') {
            eventToast('Downloads Disabled', message);
        }

        if (event === 'map_import_complete') {
            eventToast('Map import completed', message, 'success');
        }

        if (event === 'map_import_failed') {
            eventToast('Map import failed', message, 'error');
        }

        if (event === 'user_notify_message') {
            console.log(message, url);
            eventToast(
                message,
                'Click here to view the shared page',
                'info',
                10_000,
                () => window.open(url, '_self'));
        }

        if (event === 'deleted') {
            eventToast('Successful Delete', message, 'warning');
        }

        if (event === 'created') {
            eventToast('Successful Creation', message, 'success');
        }

        if (event === 'tagged') {
            eventToast('Successful tag', message, 'success');
        }

        if (subject) {
            newestEvents[subject] = dt;
        }
    })
}

export function useEventsInterval() {
    const [events, setEvents] = React.useState(null);

    // `now` is the last time we successfully fetched events.
    const now = React.useRef(localStorage.getItem('events_now'));
    const setNow = (newNow) => {
        now.current = newNow;
        localStorage.setItem('events_now', now.current);
    }

    const fetchEvents = async () => {
        try {
            const response = await getEvents(now.current);
            setNow(response['now']);
            setEvents(response['events']);
        } catch (e) {
            setEvents(null);
            console.error(e);
        }
    }

    useRecurringTimeout(fetchEvents, 1000 * 5);

    useEffect(() => {
        if (events && events.length >= 1) {
            handleEvents(events);
        }
    }, [JSON.stringify(events)]);

    return {events, fetchEvents}
}

export function useSubscribeEvents(listener) {
    // Subscribe to all API sent events.
    document.addEventListener(apiEventName, listener);
    const unsubscribe = () => document.removeEventListener(apiEventName, listener);

    useEffect(() => {
        return unsubscribe;
    }, []);
}

export function useSubscribeEventName(name, listener) {
    // Subscribe to only API sent events that match `name`.
    const localListener = (event) => {
        if (event && event.detail['event'] === name) {
            listener(event);
        }
    }

    useSubscribeEvents(localListener);
}
