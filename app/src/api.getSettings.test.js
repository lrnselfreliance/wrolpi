import {getSettings} from './api';
import {settingsFixture} from './test-fixtures';

describe('getSettings', () => {
    afterEach(() => {
        delete global.fetch;
    });

    it('keeps every setting the API sends', async () => {
        // getSettings copies each field by name, so a field the API added but nobody listed here vanished
        // silently (the Sync tab showed no backup drive while one was configured).
        const sent = settingsFixture({
            backup_directory: '/media/wrolpi_backup', backup_device_uuid: 'uuid-backup',
            role: 'secondary', sync_primary_url: 'https://10.0.0.5', sync_window_start: '01:00',
            sync_window_end: '05:00',
        });
        global.fetch = jest.fn(() => Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(sent),
            clone() {
                return this;
            },
        }));

        const settings = await getSettings();

        const dropped = Object.keys(sent).filter(key => !(key in settings));
        expect(dropped).toEqual([]);
        expect(settings.backup_directory).toBe('/media/wrolpi_backup');
        expect(settings.backup_device_uuid).toBe('uuid-backup');
    });
});
