import React, {useEffect} from 'react';
import {toast} from "react-semantic-toasts";
import {useRecurringTimeout} from "./hooks/customHooks";
import {getEvents} from "./api";


function eventToast(title, description, type = 'success', time = 5000) {
    toast({type: type, title: title, description: description, time: time});
}

function handleEvents(events) {
    const newestEvents = {};

    events.forEach(e => {
        const {event, message, subject, dt} = e;
        console.debug('event', e);

        if (subject && newestEvents[subject] && newestEvents[subject] > dt) {
            console.debug(`Already handled newer event of "${subject}".`);
            return;
        } else if (event === 'global_refresh_completed') {
            eventToast('Refresh completed', 'All files have been refreshed.');
        } else if (event === 'directory_refresh_started') {
            const description = message || 'Refresh of directory has started.';
            eventToast('Refresh started', description);
        } else if (event === 'directory_refresh_completed') {
            const description = message || 'Refresh of directory has completed.';
            eventToast('Refresh completed', description);
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
