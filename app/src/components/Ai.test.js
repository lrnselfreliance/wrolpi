import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';

import {render} from '../test-utils';
import {AiModelRow, ManageAi, llmServiceName} from './Ai';
import {Table} from './ui';

jest.mock('../api', () => ({
    getAiCatalog: jest.fn(),
    postAiSettings: jest.fn().mockResolvedValue({}),
    postDownload: jest.fn().mockResolvedValue({}),
}));
jest.mock('../api/controller', () => ({
    getServiceStatus: jest.fn().mockResolvedValue({name: 'wrolpi-llm', status: 'stopped'}),
    startService: jest.fn().mockResolvedValue({}),
    stopService: jest.fn().mockResolvedValue({}),
}));

const {getAiCatalog, postAiSettings, postDownload} = require('../api');

const catalogFixture = (overrides = {}) => ({
    models: [
        {
            name: 'Qwen3-1.7B-Q4_K_M.gguf', tier: 'small', size: 1_200_000_000,
            url: 'https://cdn.example.com/ai/Qwen3-1.7B-Q4_K_M.gguf',
            description: 'Small model.', downloaded: true, active: true,
        },
        {
            name: 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf', tier: 'medium', size: 2_600_000_000,
            url: 'https://cdn.example.com/ai/Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
            description: 'Medium model.', downloaded: false, active: false,
        },
    ],
    catalog_source: 'bundled',
    total_ram: 8 * 1024 ** 3,
    recommended_tier: 'medium',
    slow_hardware: false,
    models_directory: '/media/wrolpi/ai/models',
    disk_usage: 1_200_000_000,
    enabled: false,
    active_model: 'Qwen3-1.7B-Q4_K_M.gguf',
    idle_unload_minutes: 15,
    context_size: null,
    ...overrides,
});

describe('llmServiceName', () => {
    it('is the compose service in docker, the systemd unit natively', () => {
        expect(llmServiceName(true)).toBe('llm');
        expect(llmServiceName(false)).toBe('wrolpi-llm');
    });
});

describe('AiModelRow', () => {
    const renderRow = (model, onDownload = jest.fn()) => render(
        <Table><Table.Body><AiModelRow model={model} onDownload={onDownload}/></Table.Body></Table>);

    it('shows a downloaded, active model without a download button', () => {
        renderRow(catalogFixture().models[0]);
        expect(screen.getByText(/Qwen3-1.7B-Q4_K_M.gguf \(active\)/)).toBeInTheDocument();
        expect(screen.getByText('Downloaded')).toBeInTheDocument();
        expect(screen.queryByText('Download')).not.toBeInTheDocument();
    });

    it('offers a download for a model that is not downloaded', async () => {
        const onDownload = jest.fn();
        renderRow(catalogFixture().models[1], onDownload);
        fireEvent.click(screen.getByText('Download'));
        await waitFor(() => expect(onDownload).toHaveBeenCalled());
        expect(onDownload.mock.calls[0][0].name).toBe('Qwen3-4B-Instruct-2507-Q4_K_M.gguf');
    });
});

describe('ManageAi', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        getAiCatalog.mockResolvedValue(catalogFixture());
    });

    it('renders the catalog with the RAM recommendation', async () => {
        render(<ManageAi/>);
        await waitFor(() => expect(screen.getByText(/tier is recommended/)).toBeInTheDocument());
        // The active model appears in both the Select and its catalog row.
        expect(screen.getAllByText(/Qwen3-1.7B-Q4_K_M.gguf/).length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText(/of RAM/)).toBeInTheDocument();
    });

    it('starts a model download with the ai_model downloader', async () => {
        render(<ManageAi/>);
        await waitFor(() => expect(screen.getByText('Download')).toBeInTheDocument());
        fireEvent.click(screen.getByText('Download'));
        await waitFor(() => expect(postDownload).toHaveBeenCalled());
        expect(postDownload).toHaveBeenCalledWith({
            urls: ['https://cdn.example.com/ai/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'],
            downloader: 'ai_model',
            destination: 'ai/models',
        });
    });

    it('saves the enabled toggle', async () => {
        render(<ManageAi/>);
        await waitFor(() => expect(screen.getByLabelText('Enabled')).toBeInTheDocument());
        fireEvent.click(screen.getByLabelText('Enabled'));
        await waitFor(() => expect(postAiSettings).toHaveBeenCalledWith({enabled: true}));
    });

    it('shows the slow-hardware warning on a Pi 4', async () => {
        getAiCatalog.mockResolvedValue(catalogFixture({slow_hardware: true}));
        render(<ManageAi/>);
        await waitFor(() => expect(screen.getByText(/run the assistant slowly/)).toBeInTheDocument());
    });
});
