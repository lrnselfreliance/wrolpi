import React, {createContext, useContext, useState, useEffect, useCallback, useRef} from 'react';
import {fetchFilesProgress} from '../api';

const FileWorkerStatusContext = createContext(null);

export function FileWorkerStatusProvider({children, pollInterval = 3000}) {
    const [status, setStatus] = useState(null);
    const [error, setError] = useState(null);
    const requestedInterval = useRef(pollInterval);

    const refresh = useCallback(async () => {
        try {
            const data = await fetchFilesProgress();
            setStatus(data);
            setError(null);
        } catch (err) {
            setError(err);
        }
    }, []);

    // Allow components to request faster polling temporarily
    const setFastPolling = useCallback((fast) => {
        requestedInterval.current = fast ? 500 : pollInterval;
    }, [pollInterval]);

    useEffect(() => {
        let timeoutId;
        const poll = async () => {
            await refresh();
            timeoutId = setTimeout(poll, requestedInterval.current);
        };
        poll();
        return () => clearTimeout(timeoutId);
    }, [refresh]);

    return (
        <FileWorkerStatusContext.Provider value={{status, error, refresh, setFastPolling}}>
            {children}
        </FileWorkerStatusContext.Provider>
    );
}

export function useFileWorkerStatus() {
    const context = useContext(FileWorkerStatusContext);
    if (!context) {
        throw new Error('useFileWorkerStatus must be used within FileWorkerStatusProvider');
    }
    return context;
}

// Convenience hook for reorganization-specific status
export function useReorganizationStatus() {
    const {status: progress, refresh} = useFileWorkerStatus();

    const isReorganizing = progress?.status === 'reorganizing' ||
                          progress?.status === 'batch_reorganizing';

    return {
        isReorganizing,
        taskType: progress?.task_type,
        collectionId: progress?.collection_id,
        collectionKind: progress?.collection_kind,
        batchStatus: progress?.batch_status,
        workerStatus: progress,
        refresh,
    };
}
