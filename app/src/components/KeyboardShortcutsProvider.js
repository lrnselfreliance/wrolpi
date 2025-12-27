import React, {useCallback, useEffect, useRef, useState} from "react";
import {useNavigate} from "react-router";
import {useHotkeys} from "react-hotkeys-hook";
import {KeyboardShortcutsContext} from "../contexts/KeyboardShortcutsContext";
import {Modal} from "./Theme";
import {SearchResultsInput} from "./Common";
import {useSearchSuggestions} from "./Search";
import HelpModal from "./HelpModal";

// Define all keyboard shortcuts with their metadata
export const SHORTCUTS = [
    // Search & Help
    {keys: 'meta+k, ctrl+k', description: 'Open search', category: 'Search'},
    {keys: '/', description: 'Open search', category: 'Search', enableOnFormTags: false},
    {keys: 'escape', description: 'Close modal', category: 'General'},
    {keys: 'shift+/', description: 'Show keyboard shortcuts', category: 'Help'},

    // Navigation (g+ sequences)
    {keys: 'g h', description: 'Go to Home', category: 'Navigation', path: '/'},
    {keys: 'g v', description: 'Go to Videos', category: 'Navigation', path: '/videos'},
    {keys: 'g a', description: 'Go to Archives', category: 'Navigation', path: '/archive'},
    {keys: 'g m', description: 'Go to Map', category: 'Navigation', path: '/map'},
    {keys: 'g z', description: 'Go to Zim', category: 'Navigation', path: '/zim'},
    {keys: 'g f', description: 'Go to Files', category: 'Navigation', path: '/files'},
    {keys: 'g s', description: 'Go to Settings', category: 'Navigation', path: '/admin'},
    {keys: 'g i', description: 'Go to Inventory', category: 'Navigation', path: '/inventory'},
];

function SearchModal({open, onClose}) {
    const {
        suggestionsResults,
        handleResultSelect,
        resultRenderer,
        loading,
        searchStr,
        setSearchStr,
    } = useSearchSuggestions();

    const inputRef = useRef();
    const prevOpen = useRef(open);

    const localHandleResultSelect = (i) => {
        onClose();
        handleResultSelect(i);
    };

    useEffect(() => {
        if (prevOpen.current === true && !open) {
            // User has closed the modal.
            setSearchStr('');
        }
        prevOpen.current = open;
    }, [open, setSearchStr]);

    useEffect(() => {
        // Focus on the Search's <input/> when the modal is opened.
        if (open && inputRef.current) {
            inputRef.current.focus();
        }
    }, [open]);

    if (!open) return null;

    return (
        <Modal open={open} onClose={onClose} centered={false}>
            <Modal.Content>
                <SearchResultsInput
                    clearable
                    searchStr={searchStr}
                    onChange={setSearchStr}
                    onSubmit={setSearchStr}
                    size='large'
                    placeholder='Search everywhere...'
                    results={suggestionsResults}
                    handleResultSelect={localHandleResultSelect}
                    resultRenderer={resultRenderer}
                    loading={loading}
                    inputRef={inputRef}
                />
            </Modal.Content>
        </Modal>
    );
}

export function KeyboardShortcutsProvider({children}) {
    const navigate = useNavigate();
    const [searchModalOpen, setSearchModalOpen] = useState(false);
    const [helpModalOpen, setHelpModalOpen] = useState(false);

    const openSearchModal = useCallback(() => {
        setHelpModalOpen(false);
        setSearchModalOpen(true);
    }, []);

    const closeSearchModal = useCallback(() => {
        setSearchModalOpen(false);
    }, []);

    const openHelpModal = useCallback(() => {
        setSearchModalOpen(false);
        setHelpModalOpen(true);
    }, []);

    const closeHelpModal = useCallback(() => {
        setHelpModalOpen(false);
    }, []);

    const closeAllModals = useCallback(() => {
        setSearchModalOpen(false);
        setHelpModalOpen(false);
    }, []);

    // Search shortcuts - Cmd/Ctrl+K works everywhere
    useHotkeys('meta+k, ctrl+k', (e) => {
        e.preventDefault();
        openSearchModal();
    }, {
        enableOnFormTags: true,
        preventDefault: true,
    });

    // / for search - only when not in an input field
    // Use 'Slash' (the keyboard code) for cross-browser compatibility
    useHotkeys('Slash', (e) => {
        // Only trigger for / not ? (shift+/)
        if (e.shiftKey) return;
        e.preventDefault();
        openSearchModal();
    }, {
        enableOnFormTags: false,
    });

    // Escape closes any modal - works in inputs too
    useHotkeys('escape', () => {
        closeAllModals();
    }, {
        enableOnFormTags: true,
    });

    // ? for help modal - use shift+Slash
    useHotkeys('shift+Slash', (e) => {
        e.preventDefault();
        openHelpModal();
    }, {
        enableOnFormTags: false,
        preventDefault: true,
    });

    // Navigation shortcuts (g+ sequences) - custom implementation
    // react-hotkeys-hook doesn't handle sequences well, so we implement our own
    const gPressedRef = useRef(false);
    const gTimeoutRef = useRef(null);

    const NAV_KEYS = {
        'h': '/',
        'v': '/videos',
        'a': '/archive',
        'm': '/map',
        'z': '/zim',
        'f': '/files',
        's': '/admin',
        'i': '/inventory',
    };

    useEffect(() => {
        const handleKeyDown = (e) => {
            // Don't trigger in input fields
            const tagName = e.target.tagName.toLowerCase();
            if (tagName === 'input' || tagName === 'textarea' || tagName === 'select' || e.target.isContentEditable) {
                return;
            }

            if (e.key === 'g' && !e.metaKey && !e.ctrlKey && !e.altKey) {
                gPressedRef.current = true;
                // Clear after 1 second
                if (gTimeoutRef.current) clearTimeout(gTimeoutRef.current);
                gTimeoutRef.current = setTimeout(() => {
                    gPressedRef.current = false;
                }, 1000);
                return;
            }

            if (gPressedRef.current && NAV_KEYS[e.key]) {
                e.preventDefault();
                gPressedRef.current = false;
                if (gTimeoutRef.current) clearTimeout(gTimeoutRef.current);
                navigate(NAV_KEYS[e.key]);
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            if (gTimeoutRef.current) clearTimeout(gTimeoutRef.current);
        };
    }, [navigate]);

    const value = {
        searchModalOpen,
        setSearchModalOpen,
        openSearchModal,
        closeSearchModal,
        helpModalOpen,
        setHelpModalOpen,
        openHelpModal,
        closeHelpModal,
        closeAllModals,
    };

    return (
        <KeyboardShortcutsContext.Provider value={value}>
            {children}
            <SearchModal open={searchModalOpen} onClose={closeSearchModal}/>
            <HelpModal open={helpModalOpen} onClose={closeHelpModal}/>
        </KeyboardShortcutsContext.Provider>
    );
}
