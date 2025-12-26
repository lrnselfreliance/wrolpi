import React, {useCallback, useEffect, useRef, useState} from "react";
import {createMedia} from "@artsy/fresnel";

// Touch device detection hook (defined here to avoid circular import with customHooks)
export const useIsTouchDevice = () => {
    const [isTouchDevice, setIsTouchDevice] = useState(false);

    useEffect(() => {
        // Check if matchMedia is available (not in jsdom test environment)
        if (typeof window.matchMedia !== 'function') return;

        const touchQuery = window.matchMedia('(pointer: coarse)');
        // Guard against matchMedia returning null/undefined
        if (!touchQuery) return;

        setIsTouchDevice(touchQuery.matches);
        const handleChange = (e) => setIsTouchDevice(e.matches);
        touchQuery.addEventListener('change', handleChange);
        return () => touchQuery.removeEventListener('change', handleChange);
    }, []);

    return isTouchDevice;
};

/** @type {React.Context<import('../types/theme').ThemeContextValue>} */
export const ThemeContext = React.createContext({
    theme: 'light',
    i: {},
    s: {},
    t: {},
    inverted: '',
    savedTheme: null,
    setDarkTheme: () => {},
    setLightTheme: () => {},
    cycleSavedTheme: () => {},
});

export const StatusContext = React.createContext({
    status: {},
    fetchStatus: null,
});

export const SettingsContext = React.createContext({
    settings: {},
    fetchSettings: null,
    saveSettings: null,
    pending: false,
});

// `useQuery`
export const QueryContext = React.createContext({
    searchParams: null,
    setSearchParams: null,
    updateQuery: null,
    getLocationStr: null,
});

export const AppMedia = createMedia({
    breakpoints: {
        mobile: 0, tablet: 700, computer: 1024,
    }
});
export const mediaStyles = AppMedia.createMediaStyle();
export const {Media, MediaContextProvider} = AppMedia;

// Flatten browseFiles tree into ordered list of paths for drag selection
// Must match the sort order used by SortableTable (default: path alphabetically)
function flattenBrowseFiles(files, openFolders) {
    const result = [];
    const traverse = (items) => {
        if (!items) return;
        const itemList = Array.isArray(items) ? items : Object.values(items);
        // Sort alphabetically by path (lowercase) to match SortableTable default sort
        const sortedItems = [...itemList].sort((a, b) =>
            a.path.toLowerCase().localeCompare(b.path.toLowerCase())
        );
        sortedItems.forEach(item => {
            result.push(item.path);
            if (item.children && openFolders && openFolders.includes(item.path)) {
                traverse(item.children);
            }
        });
    };
    traverse(files);
    return result;
}

// Drag Selection Context for FileBrowser
export const DragSelectionContext = React.createContext({
    isDragging: false,
    handleDragStart: () => {},
    handleDragMove: () => {},
    getDragState: () => ({isDragSelecting: false, isDragDeselecting: false}),
});

export function DragSelectionProvider({children, selectedPaths, setSelectedPaths, browseFiles, openFolders}) {
    const DRAG_THRESHOLD = 5; // Pixels to move before considering it a drag

    // Drag selection state
    const isTouchDevice = useIsTouchDevice();
    const [isDragging, setIsDragging] = useState(false);
    const [dragStartPath, setDragStartPath] = useState(null);
    const [dragSelection, setDragSelection] = useState(new Set());
    const [dragMode, setDragMode] = useState('select'); // 'select' or 'deselect'
    const allRowPathsRef = useRef([]);
    const dragStartPosRef = useRef({x: 0, y: 0});

    // Update ordered list of visible row paths when files change
    useEffect(() => {
        if (browseFiles) {
            allRowPathsRef.current = flattenBrowseFiles(browseFiles, openFolders);
        }
    }, [browseFiles, openFolders]);

    // Drag selection handlers
    const handleDragStart = useCallback((path, event) => {
        // Only start drag on left mouse button, and not on touch devices
        if (isTouchDevice || event.button !== 0) return;

        // Don't start drag if clicking on checkbox or inside it
        if (event.target.closest('input[type="checkbox"]') || event.target.closest('.ui.checkbox')) return;

        // Determine mode: if starting from selected item, we're deselecting; otherwise selecting
        const mode = selectedPaths.includes(path) ? 'deselect' : 'select';

        dragStartPosRef.current = {x: event.clientX, y: event.clientY};
        setDragStartPath(path);
        setDragSelection(new Set([path]));
        setDragMode(mode);
    }, [isTouchDevice, selectedPaths]);

    const handleDragMove = useCallback((path) => {
        if (!dragStartPath) return;

        // Check if we've moved enough to consider it a drag
        if (!isDragging) return;

        // Calculate all paths between dragStartPath and current path
        const allPaths = allRowPathsRef.current;
        const startIndex = allPaths.indexOf(dragStartPath);
        const currentIndex = allPaths.indexOf(path);

        if (startIndex === -1 || currentIndex === -1) return;

        const minIndex = Math.min(startIndex, currentIndex);
        const maxIndex = Math.max(startIndex, currentIndex);

        // Update drag selection to include all paths in range
        setDragSelection(new Set(allPaths.slice(minIndex, maxIndex + 1)));
    }, [isDragging, dragStartPath]);

    const handleDragEnd = useCallback(() => {
        if (!isDragging && !dragStartPath) return;

        const draggedPaths = Array.from(dragSelection);
        if (draggedPaths.length > 0 && isDragging) {
            let newSelectedPaths;
            if (dragMode === 'deselect') {
                // Remove dragged paths from selection
                newSelectedPaths = selectedPaths.filter(p => !dragSelection.has(p));
            } else {
                // Add dragged paths to selection (use Set to avoid duplicates)
                newSelectedPaths = [...new Set([...selectedPaths, ...draggedPaths])];
            }
            setSelectedPaths(newSelectedPaths);
        }

        // Reset drag state
        setIsDragging(false);
        setDragStartPath(null);
        setDragSelection(new Set());
        setDragMode('select');
    }, [isDragging, dragStartPath, selectedPaths, dragSelection, dragMode, setSelectedPaths]);

    // Global mouse event listeners for drag selection
    useEffect(() => {
        if (!dragStartPath) return;

        const handleGlobalMouseMove = (e) => {
            if (!isDragging && dragStartPath) {
                // Check if we've moved enough to start dragging
                const dx = e.clientX - dragStartPosRef.current.x;
                const dy = e.clientY - dragStartPosRef.current.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance > DRAG_THRESHOLD) {
                    setIsDragging(true);
                }
            }
        };

        const handleGlobalMouseUp = () => handleDragEnd();
        const handleSelectStart = (e) => {
            if (isDragging) e.preventDefault();
        };

        document.addEventListener('mousemove', handleGlobalMouseMove);
        document.addEventListener('mouseup', handleGlobalMouseUp);
        document.addEventListener('selectstart', handleSelectStart);

        return () => {
            document.removeEventListener('mousemove', handleGlobalMouseMove);
            document.removeEventListener('mouseup', handleGlobalMouseUp);
            document.removeEventListener('selectstart', handleSelectStart);
        };
    }, [dragStartPath, isDragging, handleDragEnd, DRAG_THRESHOLD]);

    // Helper function for components to compute their visual drag state
    const getDragState = useCallback((path, isSelected) => {
        const inDragRange = dragSelection.has(path);
        const isDragSelecting = inDragRange && dragMode === 'select';
        const isDragDeselecting = inDragRange && dragMode === 'deselect' && isSelected;
        return {isDragSelecting, isDragDeselecting};
    }, [dragSelection, dragMode]);

    const value = {
        isDragging,
        handleDragStart,
        handleDragMove,
        getDragState,
    };

    return (
        <DragSelectionContext.Provider value={value}>
            {children}
        </DragSelectionContext.Provider>
    );
}
