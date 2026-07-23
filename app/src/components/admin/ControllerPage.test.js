import React from 'react';
import {render, screen, waitFor} from '@testing-library/react';
import {BrowserRouter} from 'react-router';
import {ThemeContext, SettingsContext} from '../../contexts/contexts';
import {ControllerPage} from './ControllerPage';

// Mock the controller API
jest.mock('../../api/controller', () => ({
    getServices: jest.fn().mockResolvedValue([
        {
            name: 'wrolpi-api',
            port: 8081,
            status: 'running',
            viewable: true,
            view_path: '/docs',
            enabled: true,
            kind: 'persistent',
            group: 'core',
        },
        {
            name: 'wrolpi-app',
            port: 3000,
            status: 'running',
            viewable: true,
            view_path: '',
            enabled: true,
            kind: 'persistent',
            group: 'core',
        },
        {
            name: 'smbd',
            port: 445,
            status: 'stopped',
            viewable: false,
            view_path: '',
            enabled: false,
            kind: 'persistent',
            group: 'optional',
        },
        {
            name: 'wrolpi-repair',
            port: null,
            status: 'stopped',
            viewable: false,
            view_path: '',
            enabled: false,
            kind: 'task',
            group: 'optional',
        },
    ]),
    startService: jest.fn().mockResolvedValue({success: true}),
    stopService: jest.fn().mockResolvedValue({success: true}),
    restartService: jest.fn().mockResolvedValue({success: true}),
    enableService: jest.fn().mockResolvedValue({success: true}),
    disableService: jest.fn().mockResolvedValue({success: true}),
    getServiceLogs: jest.fn().mockResolvedValue({logs: 'Sample log output'}),
    getDisks: jest.fn().mockResolvedValue([]),
    getMounts: jest.fn().mockResolvedValue([]),
    getSmartStatus: jest.fn().mockResolvedValue({}),
    restartServices: jest.fn().mockResolvedValue({success: true}),
    getSambaStatus: jest.fn().mockResolvedValue({enabled: false, available: true, shares: []}),
    addSambaShare: jest.fn().mockResolvedValue({success: true}),
    removeSambaShare: jest.fn().mockResolvedValue({success: true}),
}));


// Mock hooks
jest.mock('../../hooks/customHooks', () => ({
    useDockerized: jest.fn().mockReturnValue(false),
    useMediaDirectory: jest.fn().mockReturnValue('/media/wrolpi'),
    useBluetooth: jest.fn().mockReturnValue({on: false, setBluetooth: jest.fn()}),
    useHotspot: jest.fn().mockReturnValue({on: true, setHotspot: jest.fn()}),
    useThrottle: jest.fn().mockReturnValue({on: false, setThrottle: jest.fn()}),
}));

// Mock Common.js components that have complex dependencies
jest.mock('../Common', () => {
    const actual = jest.requireActual('../Common');
    return {
        ...actual,
        BluetoothToggle: () => <div data-testid="bluetooth-toggle">BluetoothToggle</div>,
        HotspotToggle: () => <div data-testid="hotspot-toggle">HotspotToggle</div>,
        ThrottleToggle: () => <div data-testid="throttle-toggle">ThrottleToggle</div>,
        Toggle: ({label, checked, onChange}) => (
            <label>
                <input
                    type="checkbox"
                    checked={checked || false}
                    onChange={e => onChange && onChange(e.target.checked)}
                />
                {label}
            </label>
        ),
        APIButton: ({children, onClick, disabled}) => (
            <button onClick={onClick} disabled={disabled}>{children}</button>
        ),
        DirectorySearch: ({onSelect, value}) => (
            <input data-testid="directory-search" value={value || ''} onChange={e => onSelect && onSelect(e.target.value)}/>
        ),
    };
});

// Mock Settings.js components
jest.mock('./Settings', () => ({
    RestartButton: () => <button data-testid="restart-button">Restart</button>,
    ShutdownButton: () => <button data-testid="shutdown-button">Shutdown</button>,
}));

const defaultTheme = {
    t: {style: {}},
    inverted: false,
};

const defaultSettings = {
    settings: {},
    saveSettings: jest.fn(),
    fetchSettings: jest.fn(),
};

const renderControllerPage = () => {
    return render(
        <BrowserRouter>
            <ThemeContext.Provider value={defaultTheme}>
                <SettingsContext.Provider value={defaultSettings}>
                    <ControllerPage/>
                </SettingsContext.Provider>
            </ThemeContext.Provider>
        </BrowserRouter>
    );
};

describe('ControllerPage', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        // Reset useDockerized to false for regular tests
        const {useDockerized} = require('../../hooks/customHooks');
        useDockerized.mockReturnValue(false);
    });

    test('renders Services section', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByText('Services')).toBeInTheDocument();
        });
    });

    test('renders Disk Management section', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByText('Disk Management')).toBeInTheDocument();
        });
    });

    test('renders Hardware Controls section', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByText('Hardware Controls')).toBeInTheDocument();
        });
    });

    test('calls getServices on mount', async () => {
        const {getServices} = require('../../api/controller');
        renderControllerPage();
        // Verify getServices was called
        await waitFor(() => {
            expect(getServices).toHaveBeenCalled();
        });
    });

    test('shows Restart and Shutdown buttons in non-Docker mode', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByTestId('restart-button')).toBeInTheDocument();
            expect(screen.getByTestId('shutdown-button')).toBeInTheDocument();
        });
    });

});

describe('groupServices', () => {
    const {groupServices} = require('./ControllerPage');

    test('splits core from optional by group field', () => {
        const {core, optional} = groupServices([
            {name: 'wrolpi-api', status: 'running', group: 'core'},
            {name: 'smbd', status: 'stopped', group: 'optional'},
            {name: 'wrolpi-repair', status: 'stopped', group: 'optional'},
        ]);
        expect(core.map(s => s.name)).toEqual(['wrolpi-api']);
        expect(optional.map(s => s.name)).toEqual(['smbd', 'wrolpi-repair']);
    });

    test('treats a missing group (Docker containers) as core', () => {
        const {core, optional} = groupServices([
            {name: 'api', status: 'running'},
            {name: 'db', status: 'running'},
        ]);
        expect(core).toHaveLength(2);
        expect(optional).toHaveLength(0);
    });

    test('sorts problems first, then alphabetically, within a group', () => {
        const {core} = groupServices([
            {name: 'caddy', status: 'running', group: 'core'},
            {name: 'wrolpi-api', status: 'failed', group: 'core'},
            {name: 'wrolpi-app', status: 'running', group: 'core'},
        ]);
        expect(core.map(s => s.name)).toEqual(['wrolpi-api', 'caddy', 'wrolpi-app']);
    });
});

describe('ControllerPage in Docker mode', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        const {useDockerized} = require('../../hooks/customHooks');
        useDockerized.mockReturnValue(true);
    });

    test('hides reboot/shutdown buttons in Docker mode', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByText('Hardware Controls')).toBeInTheDocument();
        });
        // Shutdown and Restart buttons should not be visible
        expect(screen.queryByTestId('shutdown-button')).not.toBeInTheDocument();
        expect(screen.queryByTestId('restart-button')).not.toBeInTheDocument();
    });

    test('shows disk management unavailable message in Docker mode', async () => {
        renderControllerPage();
        await waitFor(() => {
            expect(screen.getByText('Disk management is not available in Docker environments.')).toBeInTheDocument();
        });
    });
});
