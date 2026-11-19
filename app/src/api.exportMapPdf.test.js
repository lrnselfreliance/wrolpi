import {ExportCancelled, exportMapPdf} from './api';

const MAP = {
    width: 60, height: 90, dpi: 300, title: 'A quadrangle', bounds: [-150, 61.125, -149.875, 61.25],
    sheet: {name: 'A quadrangle', credits: [], date: '2026-11-15'},
    layers: [{name: 'Background', blob: new Blob(['background'])}, {name: 'Water', blob: new Blob(['water'])}],
};

const reply = (status, body) => ({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve(body),
    clone() {
        return this;
    },
});

// A server whose Job says each of `jobs` in turn, and then the last of them.
function fakeServer(jobs, {pdf = new Blob(['%PDF-']), replies = {}} = {}) {
    const calls = [];
    let asked = 0;
    global.fetch = jest.fn(async (url, init = {}) => {
        const path = String(url).replace(/^.*\/api/, '');
        const method = init.method || 'GET';
        calls.push(`${method} ${path}`);
        if (replies[`${method} ${path}`]) return replies[`${method} ${path}`]();
        if (path === '/map/export') return reply(201, {export_id: 'abc'});
        if (path.startsWith('/map/export/abc/layer/')) return reply(204, null);
        if (path === '/map/export/abc/start') return reply(202, {job_id: 'job-1'});
        if (path === '/map/export/abc' && method === 'DELETE') return reply(204, null);
        if (path === '/jobs/job-1') return reply(200, {job: jobs[Math.min(asked++, jobs.length - 1)]});
        if (path === '/map/export/abc/pdf') return reply(200, pdf);
        return reply(404, {error: 'Not found'});
    });
    return calls;
}

describe('exportMapPdf', () => {
    afterEach(() => {
        delete global.fetch;
    });

    test('describes the map, sends each layer, watches the Job, and fetches the PDF', async () => {
        const pdf = new Blob(['%PDF-']);
        const calls = fakeServer([
            {status: 'pending'}, {status: 'running', progress: 12.4}, {status: 'running', progress: 75},
            {status: 'complete'},
        ], {pdf});
        const statuses = [];

        const result = await exportMapPdf(MAP, {onStatus: text => statuses.push(text), pollMs: 0});

        expect(result).toBe(pdf);
        expect(calls).toEqual([
            'POST /map/export',
            'POST /map/export/abc/layer/0',
            'POST /map/export/abc/layer/1',
            'POST /map/export/abc/start',
            'GET /jobs/job-1', 'GET /jobs/job-1', 'GET /jobs/job-1', 'GET /jobs/job-1',
            'GET /map/export/abc/pdf',
            // With the PDF in hand, the server need keep nothing of the export.
            'DELETE /map/export/abc',
        ]);
        expect(statuses).toEqual([
            'Sending the map…',
            'Sending Background (1 of 2)…',
            'Sending Water (2 of 2)…',
            'Starting the PDF…',
            'Making the PDF (12%)…',
            'Making the PDF (75%)…',
            'Fetching the PDF…',
        ]);
        // The map is described without its images, and each image is sent as it is.
        const [, described] = global.fetch.mock.calls[0];
        expect(JSON.parse(described.body)).toEqual({
            width: 60, height: 90, dpi: 300, title: 'A quadrangle', bounds: MAP.bounds, sheet: MAP.sheet,
            layers: ['Background', 'Water'],
        });
        expect(global.fetch.mock.calls[2][1].body).toBe(MAP.layers[1].blob);
    });

    test('says it is waiting when another job is in the way', async () => {
        fakeServer([...Array(5).fill({status: 'pending'}), {status: 'complete'}]);
        const statuses = [];
        await exportMapPdf(MAP, {onStatus: text => statuses.push(text), pollMs: 0});
        expect(statuses.slice(3)).toEqual([
            'Starting the PDF…', 'Starting the PDF…', 'Starting the PDF…',
            'Waiting for another job to finish…', 'Waiting for another job to finish…',
            'Fetching the PDF…',
        ]);
    });

    test('says why the map was refused', async () => {
        fakeServer([], {replies: {'POST /map/export': () => reply(400, {error: 'A map of 0x0 pixels can not be exported'})}});
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('A map of 0x0 pixels can not be exported');
    });

    test('gives the PDF without waiting for the server to remove the export', async () => {
        const pdf = new Blob(['%PDF-']);
        const calls = fakeServer([{status: 'complete'}], {
            // The server never answers.
            pdf, replies: {'DELETE /map/export/abc': () => new Promise(() => undefined)},
        });
        expect(await exportMapPdf(MAP, {pollMs: 0})).toBe(pdf);
        expect(calls.at(-1)).toBe('DELETE /map/export/abc');
    });

    test('has the server remove what was sent when the export fails', async () => {
        const calls = fakeServer([{status: 'complete'}], {
            replies: {'POST /map/export/abc/layer/1': () => Promise.reject(new Error('network'))},
        });
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('Could not reach the server');
        expect(calls.at(-1)).toBe('DELETE /map/export/abc');
    });

    test('says why the Job failed', async () => {
        const calls = fakeServer([{status: 'running', progress: 0}, {status: 'failed', error: 'The layer is 10x10'}]);
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('The layer is 10x10');
        expect(calls).not.toContain('GET /map/export/abc/pdf');
    });

    test('stops before anything is sent when it was already cancelled', async () => {
        const calls = fakeServer([{status: 'complete'}]);
        await expect(exportMapPdf(MAP, {isCancelled: () => true})).rejects.toBeInstanceOf(ExportCancelled);
        expect(calls).toEqual([]);
    });

    test('has the server remove what was sent when it is stopped while layers are sent', async () => {
        const calls = fakeServer([{status: 'complete'}]);
        // Stopped once the first layer has been sent.
        const rejected = exportMapPdf(MAP, {pollMs: 0, isCancelled: () => calls.includes('POST /map/export/abc/layer/0')});
        await expect(rejected).rejects.toBeInstanceOf(ExportCancelled);
        expect(calls).toEqual(['POST /map/export', 'POST /map/export/abc/layer/0', 'DELETE /map/export/abc']);
    });

    test('has the server stop the export when it is stopped while the PDF is made', async () => {
        const calls = fakeServer([{status: 'running', progress: 10}]);
        let polls = 0;
        const rejected = exportMapPdf(MAP, {
            pollMs: 0,
            // Stopped once the Job has been asked about twice.
            isCancelled: () => calls.includes('GET /jobs/job-1') && ++polls > 2,
        });
        await expect(rejected).rejects.toMatchObject({cancelled: true});
        // The server cancels the Job of an export which is removed.
        expect(calls.at(-1)).toBe('DELETE /map/export/abc');
        expect(calls).not.toContain('GET /map/export/abc/pdf');
    });

    test('is stopped all the same when the server can not be told', async () => {
        const calls = fakeServer([{status: 'running', progress: 10}], {
            replies: {'DELETE /map/export/abc': () => Promise.reject(new Error('network'))},
        });
        const rejected = exportMapPdf(MAP, {pollMs: 0, isCancelled: () => calls.includes('GET /jobs/job-1')});
        await expect(rejected).rejects.toBeInstanceOf(ExportCancelled);
    });

    test('is stopped in the middle of a request, which the server may never answer', async () => {
        const abort = new AbortController();
        let signals = [];
        const calls = fakeServer([{status: 'complete'}], {
            replies: {
                // A layer which is never taken: the request ends when it is stopped, as fetch's does.
                'POST /map/export/abc/layer/1': () => new Promise((resolve, reject) => {
                    signals = global.fetch.mock.calls.map(([, init]) => init?.signal);
                    abort.signal.addEventListener(
                        'abort', () => reject(Object.assign(new Error('aborted'), {name: 'AbortError'})));
                    abort.abort();
                }),
            },
        });
        const rejected = exportMapPdf(MAP, {pollMs: 0, signal: abort.signal});
        await expect(rejected).rejects.toBeInstanceOf(ExportCancelled);
        // Every request of the export could be stopped; the one which removes it can not.
        expect(signals).toEqual([abort.signal, abort.signal, abort.signal]);
        expect(calls.at(-1)).toBe('DELETE /map/export/abc');
        expect(global.fetch.mock.calls.at(-1)[1].signal).toBeUndefined();
    });

    test('a Job which someone else cancelled is a cancelled export', async () => {
        fakeServer([{status: 'cancelled'}]);
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toBeInstanceOf(ExportCancelled);
    });

    test('keeps asking when the server does not answer for a moment', async () => {
        let failures = 3;
        const calls = fakeServer([{status: 'complete'}], {
            replies: {
                'GET /jobs/job-1': () => {
                    if (failures-- > 0) return Promise.reject(new Error('network'));
                    return reply(200, {job: {status: 'complete'}});
                },
            },
        });
        await exportMapPdf(MAP, {pollMs: 0});
        expect(calls.filter(i => i === 'GET /jobs/job-1')).toHaveLength(4);
    });

    test('asks for the PDF again when the request is lost, and not when it is refused', async () => {
        const pdf = new Blob(['%PDF-']);
        let lost = 3;
        let calls = fakeServer([{status: 'complete'}], {
            replies: {
                'GET /map/export/abc/pdf': () => {
                    if (lost === 3) { lost--; return Promise.reject(new Error('network')); }
                    if (lost-- > 0) return reply(502, {error: 'Bad gateway'});
                    return reply(200, pdf);
                },
            },
        });
        expect(await exportMapPdf(MAP, {pollMs: 0})).toBe(pdf);
        expect(calls.filter(i => i === 'GET /map/export/abc/pdf')).toHaveLength(4);
        // The map was drawn, sent and made into a PDF once.
        expect(calls.filter(i => i === 'POST /map/export/abc/start')).toHaveLength(1);

        calls = fakeServer([{status: 'complete'}], {
            replies: {'GET /map/export/abc/pdf': () => reply(409, {error: 'The PDF is gone'})},
        });
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('The PDF is gone');
        expect(calls.filter(i => i === 'GET /map/export/abc/pdf')).toHaveLength(1);

        calls = fakeServer([{status: 'complete'}], {
            replies: {'GET /map/export/abc/pdf': () => Promise.reject(new Error('network'))},
        });
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('Could not fetch the PDF');
        expect(calls.filter(i => i === 'GET /map/export/abc/pdf')).toHaveLength(10);
    });

    test('gives up when the server stops answering, or has forgotten the Job', async () => {
        fakeServer([], {replies: {'GET /jobs/job-1': () => Promise.reject(new Error('network'))}});
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('Could not reach the server');
        expect(global.fetch.mock.calls.filter(([url]) => String(url).endsWith('/jobs/job-1'))).toHaveLength(10);

        fakeServer([], {replies: {'GET /jobs/job-1': () => reply(404, {error: 'unknown'})}});
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('The server forgot the export');
    });
});
