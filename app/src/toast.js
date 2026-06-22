import {toast as baseToast} from "react-semantic-toasts-2";

// Central wrapper around react-semantic-toasts-2's toast.  While the API is unreachable (offline PWA, or the
// backend is down) we swallow `error` toasts so the user gets a single calm apiDown indicator in the nav instead
// of a wall of red error toasts.  Success/info/warning toasts still show.
//
// `window.apiDown` lags the ~3s status poll, so we also check `navigator.onLine === false` to suppress instantly
// when the browser already knows it is offline.
export function toast(opts) {
    const offline = window.apiDown === true || navigator.onLine === false;
    if (offline && opts && opts.type === 'error') {
        return;
    }
    return baseToast(opts);
}
