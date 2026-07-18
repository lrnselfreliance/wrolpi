// Shared UA sniffing for the WROLPi browser extension UI.
// The extension only ships for Chromium (Chrome/Brave/Edge/Opera) and Firefox;
// Safari and other browsers should not be nudged to install it.

/**
 * @returns {'firefox' | 'chromium' | 'unknown'}
 */
export function detectBrowser() {
    if (typeof navigator === 'undefined') return 'unknown';
    const ua = navigator.userAgent || '';
    // Order matters: Edge / Brave / Opera all include 'Chrome' in their UA.
    if (ua.includes('Firefox')) return 'firefox';
    if (ua.includes('Edg/')) return 'chromium';
    if (ua.includes('OPR/') || ua.includes('Opera')) return 'chromium';
    if (ua.includes('Chrome')) return 'chromium';
    return 'unknown';
}

/** True when the current browser can run the WROLPi extension. */
export function isExtensionSupportedBrowser() {
    const browser = detectBrowser();
    return browser === 'firefox' || browser === 'chromium';
}
