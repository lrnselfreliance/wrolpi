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
    shouldAllowClick: () => true,
    // Selection state and functions
    selectedPaths: [],
    onSelect: () => {},
    isSelected: () => false,
    clearSelection: () => {},
});

export function DragSelectionProvider({children, selectedPaths, setSelectedPaths, browseFiles, openFolders}) {
    const DRAG_THRESHOLD = 5; // Pixels to move before considering it a drag

    // Drag selection state
    const isTouchDevice = useIsTouchDevice();
    const [isDragging, setIsDragging] = useState(false);
    const [isMouseDown, setIsMouseDown] = useState(false);
    const [dragStartPath, setDragStartPath] = useState(null);
    const [dragSelection, setDragSelection] = useState(new Set());
    const [dragMode, setDragMode] = useState('select'); // 'select' or 'deselect'
    const allRowPathsRef = useRef([]);
    const dragStartPosRef = useRef({x: 0, y: 0});
    // Track pending drag start - stored in refs to avoid visual changes before threshold
    const pendingDragPathRef = useRef(null);
    const pendingDragModeRef = useRef('select');
    // Track if a drag just completed - used to prevent onClick from firing after drag
    const dragJustCompletedRef = useRef(false);

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

        // Store in refs - don't set dragSelection yet to avoid visual flap
        // Visual changes only happen after drag threshold is exceeded
        dragStartPosRef.current = {x: event.clientX, y: event.clientY};
        pendingDragPathRef.current = path;
        pendingDragModeRef.current = mode;
        setIsMouseDown(true);
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
        if (!isMouseDown) return;

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
            // Mark that a drag just completed - onClick handlers should not fire
            dragJustCompletedRef.current = true;
        }

        // Reset all drag state
        setIsMouseDown(false);
        setIsDragging(false);
        setDragStartPath(null);
        setDragSelection(new Set());
        setDragMode('select');
        pendingDragPathRef.current = null;
        pendingDragModeRef.current = 'select';
    }, [isMouseDown, isDragging, selectedPaths, dragSelection, dragMode, setSelectedPaths]);

    // Global mouse event listeners for drag selection
    useEffect(() => {
        if (!isMouseDown) return;

        const handleGlobalMouseMove = (e) => {
            if (!isDragging && pendingDragPathRef.current) {
                // Check if we've moved enough to start dragging
                const dx = e.clientX - dragStartPosRef.current.x;
                const dy = e.clientY - dragStartPosRef.current.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance > DRAG_THRESHOLD) {
                    // NOW initialize drag state - this triggers visual feedback
                    setDragStartPath(pendingDragPathRef.current);
                    setDragSelection(new Set([pendingDragPathRef.current]));
                    setDragMode(pendingDragModeRef.current);
                    setIsDragging(true);
                }
            }
        };

        const handleGlobalMouseUp = () => handleDragEnd();
        const handleSelectStart = (e) => {
            if (isMouseDown) e.preventDefault();
        };

        document.addEventListener('mousemove', handleGlobalMouseMove);
        document.addEventListener('mouseup', handleGlobalMouseUp);
        document.addEventListener('selectstart', handleSelectStart);

        return () => {
            document.removeEventListener('mousemove', handleGlobalMouseMove);
            document.removeEventListener('mouseup', handleGlobalMouseUp);
            document.removeEventListener('selectstart', handleSelectStart);
        };
    }, [isMouseDown, isDragging, handleDragEnd, DRAG_THRESHOLD]);

    // Helper function for components to compute their visual drag state
    const getDragState = useCallback((path, isSelected) => {
        const inDragRange = dragSelection.has(path);
        const isDragSelecting = inDragRange && dragMode === 'select';
        const isDragDeselecting = inDragRange && dragMode === 'deselect' && isSelected;
        return {isDragSelecting, isDragDeselecting};
    }, [dragSelection, dragMode]);

    // Check if a click should be allowed (not blocked by a recent drag)
    // This is called by onClick handlers to determine if they should proceed
    const shouldAllowClick = useCallback(() => {
        if (dragJustCompletedRef.current) {
            dragJustCompletedRef.current = false;
            return false;
        }
        return true;
    }, []);

    // Selection functions - moved from FileBrowser to eliminate prop drilling
    const onSelect = useCallback((path) => {
        setSelectedPaths(prev => {
            if (prev.includes(path)) {
                return prev.filter(i => i !== path);
            }
            return [...prev, path];
        });
    }, [setSelectedPaths]);

    const isSelected = useCallback((path) => {
        return selectedPaths.includes(path);
    }, [selectedPaths]);

    const clearSelection = useCallback(() => {
        setSelectedPaths([]);
    }, [setSelectedPaths]);

    const value = {
        isDragging,
        handleDragStart,
        handleDragMove,
        getDragState,
        shouldAllowClick,
        // Selection state and functions
        selectedPaths,
        onSelect,
        isSelected,
        clearSelection,
    };

    return (
        <DragSelectionContext.Provider value={value}>
            {children}
        </DragSelectionContext.Provider>
    );
}
