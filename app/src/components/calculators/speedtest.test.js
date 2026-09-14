import {
    Buckets,
    bytesToMbps,
    describePing,
    formatMbps,
    isHotspotAddress,
    otherActiveTests,
    peakMbps,
    pingStats,
    runDownload,
    runPing,
    runUpload,
    steadyStateMbps,
    streamCapacity,
} from "./speedtest";

// A controllable clock so bucket boundaries are deterministic.
const makeClock = () => {
    let t = 0;
    const now = () => t;
    now.advance = ms => {
        t += ms;
    };
    return now;
};

describe('bytesToMbps', () => {
    test('converts bytes over milliseconds to decimal megabits per second', () => {
        // 1,250,000 bytes in one second is 10,000,000 bits/s = 10 Mbps.
        expect(bytesToMbps(1_250_000, 1000)).toBeCloseTo(10, 6);
        expect(bytesToMbps(1_250_000, 500)).toBeCloseTo(20, 6);
    });

    test('zero or negative time is zero, not infinity', () => {
        expect(bytesToMbps(100, 0)).toBe(0);
    });
});

describe('formatMbps', () => {
    test('shows more digits for slower links', () => {
        expect(formatMbps(543.21)).toBe('543');
        expect(formatMbps(54.321)).toBe('54.3');
        expect(formatMbps(5.4321)).toBe('5.43');
    });

    test('missing values are a dash', () => {
        expect(formatMbps(null)).toBe('—');
        expect(formatMbps(NaN)).toBe('—');
    });
});

describe('streamCapacity', () => {
    test('floors the measured throughput against each tier bitrate', () => {
        const rows = Object.fromEntries(streamCapacity(8).map(r => [r.key, r.streams]));
        expect(rows).toEqual({'480p': 3, '720p': 1, '1080p': 1, '1440p': 0, '2160p': 0});
    });

    test('a fast link streams many at once', () => {
        const rows = Object.fromEntries(streamCapacity(250).map(r => [r.key, r.streams]));
        expect(rows['2160p']).toBe(10);
        expect(rows['480p']).toBe(100);
    });

    test('nothing measured means zero streams everywhere', () => {
        expect(streamCapacity(0).every(r => r.streams === 0)).toBe(true);
        expect(streamCapacity(NaN).every(r => r.streams === 0)).toBe(true);
    });
});

describe('steadyStateMbps', () => {
    // 250 ms buckets; 312,500 bytes per bucket is 10 Mbps.
    const bucket = (ms, bytes) => ({ms, width: 250, bytes});

    test('ignores the ramp-up second and averages the rest', () => {
        const samples = [
            bucket(250, 0), bucket(500, 0), bucket(750, 0), bucket(1000, 0),  // slow start
            bucket(1250, 312_500), bucket(1500, 312_500), bucket(1750, 312_500), bucket(2000, 312_500),
        ];
        expect(steadyStateMbps(samples)).toBeCloseTo(10, 6);
    });

    test('falls back to the whole run when it never left the ramp window', () => {
        expect(steadyStateMbps([bucket(250, 312_500), bucket(500, 312_500)])).toBeCloseTo(10, 6);
    });

    test('empty run is zero', () => {
        expect(steadyStateMbps([])).toBe(0);
        expect(steadyStateMbps(undefined)).toBe(0);
    });

    test('peak is the fastest single bucket', () => {
        expect(peakMbps([bucket(250, 312_500), bucket(500, 625_000)])).toBeCloseTo(20, 6);
    });
});

describe('pingStats', () => {
    test('reports min, median and mean successive jitter', () => {
        const stats = pingStats([10, 12, 30, 14]);
        expect(stats.min).toBe(10);
        expect(stats.median).toBe(13);
        // |12-10| + |30-12| + |14-30| = 2 + 18 + 16 = 36; / 3 = 12.
        expect(stats.jitter).toBeCloseTo(12, 6);
        expect(stats.lost).toBe(0);
    });

    test('timeouts are counted as lost and excluded from the numbers', () => {
        const stats = pingStats([10, null, 20]);
        expect(stats.lost).toBe(1);
        expect(stats.median).toBe(15);
    });

    test('all lost gives nulls', () => {
        expect(pingStats([null, null])).toEqual({min: null, median: null, jitter: null, lost: 2});
    });
});

describe('describePing', () => {
    test('thresholds', () => {
        expect(describePing(5).text).toBe('Excellent');
        expect(describePing(40).text).toBe('Good');
        expect(describePing(100).text).toBe('Fair');
        expect(describePing(400).text).toBe('Poor');
        expect(describePing(null).text).toBe('No response');
    });
});

describe('isHotspotAddress', () => {
    test("matches NetworkManager's shared range", () => {
        expect(isHotspotAddress('10.42.0.7')).toBe(true);
        expect(isHotspotAddress('10.42.1.200')).toBe(true);
        expect(isHotspotAddress('::ffff:10.42.0.7')).toBe(true);
    });

    test('rejects LAN, loopback and garbage', () => {
        expect(isHotspotAddress('10.0.0.5')).toBe(false);
        expect(isHotspotAddress('192.168.1.10')).toBe(false);
        expect(isHotspotAddress('::1')).toBe(false);
        expect(isHotspotAddress('10.420.0.1')).toBe(false);
        expect(isHotspotAddress(undefined)).toBe(false);
    });
});

describe('otherActiveTests', () => {
    test('subtracts our own in-flight request from the during sample', () => {
        expect(otherActiveTests(0, 1)).toBe(0);
        expect(otherActiveTests(0, 3)).toBe(2);
        expect(otherActiveTests(2, 1)).toBe(2);
        expect(otherActiveTests(undefined, undefined)).toBe(0);
    });
});

describe('Buckets', () => {
    test('closes a bucket once its width has elapsed', () => {
        const now = makeClock();
        const b = new Buckets(250, now);
        b.add(100);
        expect(b.samples).toHaveLength(0);
        now.advance(250);
        b.add(200);
        expect(b.samples).toHaveLength(1);
        expect(b.samples[0]).toEqual({ms: 250, width: 250, bytes: 300});
        expect(b.total).toBe(300);
    });

    test('a stall spreads its bytes over the buckets it spanned', () => {
        const now = makeClock();
        const b = new Buckets(250, now);
        now.advance(1000);
        b.add(400);
        expect(b.samples.map(s => s.bytes)).toEqual([100, 100, 100, 100]);
    });

    test('force flush closes a partial bucket', () => {
        const now = makeClock();
        const b = new Buckets(250, now);
        now.advance(100);
        b.add(50);
        b.flush(true);
        expect(b.samples).toHaveLength(1);
        expect(b.samples[0].width).toBe(100);
        expect(b.samples[0].bytes).toBe(50);
    });
});

// A fake fetch that serves a ReadableStream of `chunks`, advancing the clock per chunk.
const streamingFetch = (chunks, now, perChunkMs) => jest.fn(async () => {
    let i = 0;
    return {
        ok: true,
        status: 200,
        body: {
            getReader: () => ({
                read: async () => {
                    if (i >= chunks.length) {
                        return {done: true};
                    }
                    now.advance(perChunkMs);
                    return {done: false, value: new Uint8Array(chunks[i++])};
                },
                cancel: async () => {
                },
            }),
        },
    };
});

describe('runDownload', () => {
    test('totals the bytes and reports steady-state throughput', async () => {
        const now = makeClock();
        // 12 chunks of 312,500 bytes, one every 250 ms: 10 Mbps for 3 s.
        const fetch = streamingFetch(Array(12).fill(312_500), now, 250);
        const progress = jest.fn();
        const result = await runDownload({seconds: 10, onProgress: progress, deps: {fetch, now}});
        expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/speedtest/download?seconds=10'),
            expect.objectContaining({cache: 'no-store'}));
        expect(result.bytes).toBe(12 * 312_500);
        expect(result.mbps).toBeCloseTo(10, 3);
        expect(progress).toHaveBeenCalled();
    });

    test('stops reading at the client deadline even if the server keeps sending', async () => {
        const now = makeClock();
        const fetch = streamingFetch(Array(100).fill(1000), now, 250);
        const result = await runDownload({seconds: 1, deps: {fetch, now}});
        // 1 s deadline / 250 ms per chunk = 4 chunks read.
        expect(result.bytes).toBe(4000);
    });

    test('a non-2xx response is an error', async () => {
        const fetch = jest.fn(async () => ({ok: false, status: 502}));
        await expect(runDownload({deps: {fetch, now: makeClock()}})).rejects.toThrow('HTTP 502');
    });
});

describe('runUpload', () => {
    test('posts until the deadline and sums the server-reported bytes', async () => {
        const now = makeClock();
        const fetch = jest.fn(async (url, init) => {
            now.advance(500);
            return {ok: true, status: 200, json: async () => ({bytes: init.body.size, seconds: 0.5})};
        });
        const body = {size: 625_000};  // 625,000 bytes per 500 ms = 10 Mbps
        const result = await runUpload({seconds: 2, body, deps: {fetch, now}});
        expect(fetch).toHaveBeenCalledTimes(4);
        expect(fetch.mock.calls[0][1]).toEqual(expect.objectContaining({method: 'POST', body}));
        expect(result.bytes).toBe(4 * 625_000);
        expect(result.mbps).toBeCloseTo(10, 3);
    });

    test('a request still in flight at the deadline is aborted and the phase ends on time', async () => {
        jest.useFakeTimers();
        try {
            const now = makeClock();
            let calls = 0;
            const fetch = jest.fn((url, init) => new Promise((resolve, reject) => {
                calls++;
                if (calls === 1) {
                    // Fast first request.
                    now.advance(200);
                    resolve({ok: true, status: 200, json: async () => ({bytes: 1000, seconds: 0.2})});
                    return;
                }
                // Second request never completes on its own: it must be aborted at the deadline.
                init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
            }));
            const promise = runUpload({seconds: 1, body: {size: 1000}, deps: {fetch, now}});
            // Let the first request settle and the second start.
            await Promise.resolve();
            await Promise.resolve();
            await Promise.resolve();
            now.advance(2000);
            jest.advanceTimersByTime(1000);
            const result = await promise;
            expect(fetch).toHaveBeenCalledTimes(2);
            expect(fetch.mock.calls[1][1].signal.aborted).toBe(true);
            // Only the completed request counts.
            expect(result.bytes).toBe(1000);
        } finally {
            jest.useRealTimers();
        }
    });

    test('an aborted signal ends the loop', async () => {
        const now = makeClock();
        const controller = new AbortController();
        const fetch = jest.fn(async () => {
            now.advance(100);
            controller.abort();
            return {ok: true, status: 200, json: async () => ({bytes: 10, seconds: 0.1})};
        });
        const result = await runUpload({seconds: 10, body: {size: 10}, signal: controller.signal, deps: {fetch, now}});
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(result.bytes).toBe(10);
    });
});

describe('runPing', () => {
    test('times each round trip and records timeouts as lost', async () => {
        const now = makeClock();
        let call = 0;
        const fetch = jest.fn(async () => {
            call++;
            now.advance(call === 2 ? 30 : 10);
            if (call === 3) {
                throw new Error('network');
            }
            return {ok: true, arrayBuffer: async () => new ArrayBuffer(0)};
        });
        const sleep = jest.fn(async () => {
        });
        const stats = await runPing({samples: 4, deps: {fetch, now, sleep}});
        expect(fetch).toHaveBeenCalledTimes(4);
        expect(stats.lost).toBe(1);
        expect(stats.min).toBe(10);
        expect(stats.median).toBe(10);
        expect(sleep).toHaveBeenCalledTimes(3);
    });
});
