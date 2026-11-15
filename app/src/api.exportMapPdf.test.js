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
        if (path === '/jobs/job-1' && method === 'DELETE') return reply(200, {job: {status: 'cancelled'}});
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

    test('cancels the Job when it is stopped while the PDF is made', async () => {
        const calls = fakeServer([{status: 'running', progress: 10}]);
        let polls = 0;
        const rejected = exportMapPdf(MAP, {
            pollMs: 0,
            // Stopped once the Job has been asked about twice.
            isCancelled: () => calls.includes('GET /jobs/job-1') && ++polls > 2,
        });
        await expect(rejected).rejects.toMatchObject({cancelled: true});
        expect(calls).toContain('DELETE /jobs/job-1');
        expect(calls).not.toContain('GET /map/export/abc/pdf');
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

    test('gives up when the server stops answering, or has forgotten the Job', async () => {
        fakeServer([], {replies: {'GET /jobs/job-1': () => Promise.reject(new Error('network'))}});
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('Could not reach the server');
        expect(global.fetch.mock.calls.filter(([url]) => String(url).endsWith('/jobs/job-1'))).toHaveLength(10);

        fakeServer([], {replies: {'GET /jobs/job-1': () => reply(404, {error: 'unknown'})}});
        await expect(exportMapPdf(MAP, {pollMs: 0})).rejects.toThrow('The server forgot the export');
    });
});
