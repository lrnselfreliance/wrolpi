import React from 'react';
import {screen} from '@testing-library/react';
import {FilesRefreshProgress} from './Files';
import {renderWithProviders} from '../test-utils';
import {fileWorkerStatusFixture} from '../test-fixtures';
import {FileWorkerStatusContext} from '../contexts/FileWorkerStatusContext';

const renderProgress = (status) => renderWithProviders(
    <FileWorkerStatusContext.Provider value={fileWorkerStatusFixture({status})}>
        <FilesRefreshProgress/>
    </FileWorkerStatusContext.Provider>
);

const moving = {
    status: 'moving',
    task_type: 'move',
    destination: '/media/wrolpi/3d models/Tools',
    operation_total: 109,
    operation_processed: 40,
    operation_percent: 36,
    error: null,
};

describe('FilesRefreshProgress', () => {
    it('labels a move', () => {
        renderProgress({...moving, rename_from: null});
        expect(screen.getByText('Move: Moving (40 / 109)')).toBeInTheDocument();
    });

    it('labels a directory rename with the renamed directory', () => {
        renderProgress({...moving, rename_from: '/media/wrolpi/3d models/tools'});
        expect(screen.getByText('Rename tools: Moving (40 / 109)')).toBeInTheDocument();
    });

    it('labels a directory rename that is planning', () => {
        renderProgress({...moving, status: 'planning', operation_total: 0, rename_from: '/media/wrolpi/3d models/tools'});
        expect(screen.getByText('Rename tools: Planning')).toBeInTheDocument();
    });

    it('shows nothing while idle', () => {
        renderProgress({...moving, status: 'idle'});
        expect(screen.queryByText(/Move|Rename/)).not.toBeInTheDocument();
    });
});
