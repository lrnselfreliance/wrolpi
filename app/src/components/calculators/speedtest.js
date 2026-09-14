/**
 * Speed test logic with no React in it, so Jest can drive it with fake fetch/streams.
 *
 * Units: Mbps means decimal megabits per second (1 Mbps = 1,000,000 bits/s), the unit video
 * bitrates are quoted in.  MB/s is decimal megabytes.
 */
import {API_URI} from "../Vars";

export const SPEEDTEST_API = `${API_URI}/speedtest`;

// The browser runs each throughput phase this long.  The server clamps download at 15 s.
export const PHASE_SECONDS = 10;
// Throughput is tallied into buckets this wide; the live number and sparkline are per bucket.
export const BUCKET_MS = 250;
// TCP ramps up over the first second; the steady-state figure ignores it.
export const RAMP_MS = 1000;
export const PING_SAMPLES = 20;
export const PING_GAP_MS = 100;
export const PING_TIMEOUT_MS = 5000;
// One body reused for every upload POST.  Under the server's 8 MiB cap.
export const UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024;

// Typical bitrates for a well-encoded video at each resolution.  Deliberately round; the table
// says "about".
export const STREAM_TIERS = [
    {key: '480p', label: '480p (SD)', mbps: 2.5},
    {key: '720p', label: '720p (HD)', mbps: 5},
    {key: '1080p', label: '1080p (Full HD)', mbps: 8},
    {key: '1440p', label: '1440p (2K)', mbps: 16},
    {key: '2160p', label: '2160p (4K)', mbps: 25},
];

export const bytesToMbps = (bytes, ms) => ms > 0 ? (bytes * 8) / (ms / 1000) / 1e6 : 0;

export const mbpsToMBps = mbps => mbps / 8;

export function formatMbps(mbps) {
    if (mbps === null || mbps === undefined || !Number.isFinite(mbps)) {
        return '—';
    }
    if (mbps >= 100) {
        return mbps.toFixed(0);
    }
    return mbps >= 10 ? mbps.toFixed(1) : mbps.toFixed(2);
}

export function formatMs(ms) {
    if (ms === null || ms === undefined || !Number.isFinite(ms)) {
        return '—';
    }
    return ms >= 100 ? ms.toFixed(0) : ms.toFixed(1);
}

/**
 * How many simultaneous streams of each tier fit in the measured download throughput.
 */
export function streamCapacity(downloadMbps) {
    const mbps = Number.isFinite(downloadMbps) && downloadMbps > 0 ? downloadMbps : 0;
    return STREAM_TIERS.map(tier => ({...tier, streams: Math.floor(mbps / tier.mbps)}));
}

/**
 * Average the per-bucket throughput after the ramp-up window.  `samples` are
 * `{ms, bytes}` buckets in order, `ms` being the bucket's end offset from the phase start.
 * Falls back to the whole run when it was too short to have a steady state.
 */
export function steadyStateMbps(samples) {
    if (!samples || samples.length === 0) {
        return 0;
    }
    let steady = samples.filter(s => s.ms > RAMP_MS);
    if (steady.length === 0) {
        steady = samples;
    }
    const bytes = steady.reduce((acc, s) => acc + s.bytes, 0);
    const first = steady[0];
    const start = first.ms - first.width;
    const ms = steady[steady.length - 1].ms - start;
    return bytesToMbps(bytes, ms);
}

export const peakMbps = samples => Math.max(0, ...(samples || []).map(s => bytesToMbps(s.bytes, s.width)));

export function pingStats(rtts) {
    const good = (rtts || []).filter(Number.isFinite);
    if (good.length === 0) {
        return {min: null, median: null, jitter: null, lost: (rtts || []).length};
    }
    const sorted = [...good].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    let jitter = 0;
    if (good.length > 1) {
        let diffs = 0;
        for (let i = 1; i < good.length; i++) {
            diffs += Math.abs(good[i] - good[i - 1]);
        }
        jitter = diffs / (good.length - 1);
    }
    return {min: sorted[0], median, jitter, lost: (rtts || []).length - good.length};
}

export function describePing(medianMs) {
    if (medianMs === null || medianMs === undefined || !Number.isFinite(medianMs)) {
        return {kind: 'warning', text: 'No response'};
    }
    if (medianMs < 20) {
        return {kind: 'success', text: 'Excellent'};
    }
    if (medianMs < 60) {
        return {kind: 'success', text: 'Good'};
    }
    if (medianMs < 150) {
        return {kind: 'warning', text: 'Fair'};
    }
    return {kind: 'danger', text: 'Poor'};
}

/**
 * NetworkManager's shared-connection mode (which `nmcli device wifi hotspot` uses) hands out
 * 10.42.x.x addresses.
 */
export function isHotspotAddress(ip) {
    if (!ip || typeof ip !== 'string') {
        return false;
    }
    const v4 = ip.startsWith('::ffff:') ? ip.slice(7) : ip;
    return /^10\.42\.\d{1,3}\.\d{1,3}$/.test(v4);
}

/**
 * Accumulates byte counts into fixed-width buckets and reports them for the live display.
 */
export class Buckets {
    constructor(width = BUCKET_MS, now = () => performance.now()) {
        this.width = width;
        this.now = now;
        this.start = now();
        this.samples = [];
        this.pending = 0;
        this.total = 0;
    }

    add(bytes) {
        this.pending += bytes;
        this.total += bytes;
        this.flush(false);
    }

    /** Close every bucket that has fully elapsed (or all of them when `force`). */
    flush(force) {
        const elapsed = this.now() - this.start;
        const closed = this.samples.length * this.width;
        if (elapsed - closed >= this.width) {
            // Every complete bucket since the last flush gets the pending bytes.  Almost always
            // this is one bucket; a stall spreads its bytes over the buckets it spanned.
            const count = Math.floor((elapsed - closed) / this.width);
            const per = this.pending / count;
            for (let i = 1; i <= count; i++) {
                this.samples.push({ms: closed + i * this.width, width: this.width, bytes: per});
            }
            this.pending = 0;
        } else if (force && this.pending > 0) {
            const width = Math.max(1, elapsed - closed);
            this.samples.push({ms: elapsed, width, bytes: this.pending});
            this.pending = 0;
        }
    }

    get elapsedMs() {
        return this.now() - this.start;
    }

    /** Mbps of the most recently closed bucket, for the big live number. */
    get currentMbps() {
        const last = this.samples[this.samples.length - 1];
        return last ? bytesToMbps(last.bytes, last.width) : 0;
    }
}

const defaultDeps = () => ({
    fetch: (...args) => window.fetch(...args),
    now: () => performance.now(),
    sleep: ms => new Promise(resolve => setTimeout(resolve, ms)),
});

/**
 * Time PING_SAMPLES sequential round trips.  Calls `onSample(rtts)` after each.
 * A sample that times out is recorded as `null`.
 */
export async function runPing({signal, onSample, samples = PING_SAMPLES, gapMs = PING_GAP_MS, deps} = {}) {
    const {fetch, now, sleep} = {...defaultDeps(), ...deps};
    const rtts = [];
    for (let i = 0; i < samples; i++) {
        if (signal?.aborted) {
            break;
        }
        const timeout = new AbortController();
        const timer = setTimeout(() => timeout.abort(), PING_TIMEOUT_MS);
        const onAbort = () => timeout.abort();
        signal?.addEventListener('abort', onAbort);
        const start = now();
        try {
            const response = await fetch(`${SPEEDTEST_API}/ping`, {cache: 'no-store', signal: timeout.signal});
            await response.arrayBuffer();
            rtts.push(response.ok ? now() - start : null);
        } catch (e) {
            if (signal?.aborted) {
                break;
            }
            rtts.push(null);
        } finally {
            clearTimeout(timer);
            signal?.removeEventListener('abort', onAbort);
        }
        if (onSample) {
            onSample([...rtts]);
        }
        if (i < samples - 1) {
            await sleep(gapMs);
        }
    }
    return pingStats(rtts);
}

/**
 * Read a download stream for `seconds`, tallying bytes into buckets.  Calls `onProgress(buckets)`
 * as data arrives.  Resolves to `{mbps, peak, bytes, samples}`.
 */
export async function runDownload({signal, onProgress, seconds = PHASE_SECONDS, deps} = {}) {
    const {fetch, now} = {...defaultDeps(), ...deps};
    const buckets = new Buckets(BUCKET_MS, now);
    // The server also stops at `seconds`; the client deadline covers a slow last chunk.
    const deadline = buckets.start + seconds * 1000;
    const response = await fetch(`${SPEEDTEST_API}/download?seconds=${seconds}`, {cache: 'no-store', signal});
    if (!response.ok) {
        throw new Error(`Download test failed: HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    try {
        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                break;
            }
            buckets.add(value.byteLength);
            if (onProgress) {
                onProgress(buckets);
            }
            if (now() >= deadline) {
                break;
            }
        }
    } finally {
        try {
            await reader.cancel();
        } catch (e) {
            // Already closed.
        }
    }
    buckets.flush(true);
    return {mbps: steadyStateMbps(buckets.samples), peak: peakMbps(buckets.samples), bytes: buckets.total, samples: buckets.samples};
}

export function randomBlob(size = UPLOAD_CHUNK_BYTES) {
    const bytes = new Uint8Array(size);
    // getRandomValues refuses more than 64 KiB per call.
    const step = 65536;
    for (let offset = 0; offset < size; offset += step) {
        window.crypto.getRandomValues(bytes.subarray(offset, Math.min(offset + step, size)));
    }
    return new Blob([bytes], {type: 'application/octet-stream'});
}

/**
 * POST the same random body over and over for `seconds`, tallying the bytes each request
 * delivered.  Sequential requests rather than a streamed body because Safari cannot stream a
 * request body.  Resolves to `{mbps, peak, bytes, samples}`.
 */
export async function runUpload({signal, onProgress, seconds = PHASE_SECONDS, body, deps} = {}) {
    const {fetch, now} = {...defaultDeps(), ...deps};
    const blob = body || randomBlob();
    const buckets = new Buckets(BUCKET_MS, now);
    const deadline = buckets.start + seconds * 1000;
    while (now() < deadline && !signal?.aborted) {
        const response = await fetch(`${SPEEDTEST_API}/upload`, {method: 'POST', body: blob, cache: 'no-store', signal});
        if (!response.ok) {
            throw new Error(`Upload test failed: HTTP ${response.status}`);
        }
        const json = await response.json();
        buckets.add(json.bytes);
        if (onProgress) {
            onProgress(buckets);
        }
    }
    buckets.flush(true);
    return {mbps: steadyStateMbps(buckets.samples), peak: peakMbps(buckets.samples), bytes: buckets.total, samples: buckets.samples};
}

export async function fetchInfo({deps} = {}) {
    const {fetch} = {...defaultDeps(), ...deps};
    const response = await fetch(`${SPEEDTEST_API}/info`, {cache: 'no-store'});
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
}

/** "2 other tests" given the counter sampled before and during our own run. */
export function otherActiveTests(before, during) {
    const b = Number.isFinite(before) ? before : 0;
    // While our own download or upload is in flight the counter includes us.
    const d = Number.isFinite(during) ? Math.max(0, during - 1) : 0;
    return Math.max(b, d);
}
