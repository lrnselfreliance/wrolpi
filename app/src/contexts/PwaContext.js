import React, {useContext, useEffect, useMemo, useState} from "react";
import {StatusContext} from "./contexts";

// Cross-cutting PWA state, consumed anywhere via usePwa() instead of prop-drilling.
//
//   offline      - true when the browser is offline or the API is unreachable.  Inventory (and other) reads are
//                  served from the service-worker cache, but writes can't reach the backend, so editing UI is
//                  disabled while this is true.
//   isStandalone - true when launched as an installed PWA (Add to Home Screen / standalone display mode).
//
// The default value (offline: false) means components rendered outside a PwaProvider — e.g. in unit tests — behave
// as if online, so they need no provider wrapper.
export const PwaContext = React.createContext({
    offline: false,
    isStandalone: false,
});

const computeOffline = () =>
    (typeof navigator !== 'undefined' && navigator.onLine === false) || window.apiDown === true;

const computeStandalone = () =>
    (typeof window !== 'undefined') && (
        (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
        window.navigator.standalone === true
    );

export function PwaProvider({children}) {
    // Consuming StatusContext makes this provider re-render on every status poll, so window.apiDown (set imperatively
    // by useStatus) is picked up without a dedicated interval.
    const {status} = useContext(StatusContext);

    const [offline, setOffline] = useState(computeOffline);
    const [isStandalone] = useState(computeStandalone);

    // Instant updates when connectivity flips (the store-aisle case: network drops).
    useEffect(() => {
        const update = () => setOffline(computeOffline());
        window.addEventListener('online', update);
        window.addEventListener('offline', update);
        return () => {
            window.removeEventListener('online', update);
            window.removeEventListener('offline', update);
        };
    }, []);

    // Re-sync on each status poll to catch the network-up / API-down case.
    useEffect(() => {
        setOffline(computeOffline());
    }, [status]);

    const value = useMemo(() => ({offline, isStandalone}), [offline, isStandalone]);

    return <PwaContext.Provider value={value}>{children}</PwaContext.Provider>;
}

export function usePwa() {
    return useContext(PwaContext);
}
