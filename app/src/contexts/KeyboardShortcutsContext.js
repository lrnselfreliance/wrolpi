import React from "react";

// Keyboard shortcuts context for managing global shortcuts and modal states
export const KeyboardShortcutsContext = React.createContext({
    // Search modal state
    searchModalOpen: false,
    setSearchModalOpen: () => {},
    openSearchModal: () => {},
    closeSearchModal: () => {},

    // Help modal state
    helpModalOpen: false,
    setHelpModalOpen: () => {},
    openHelpModal: () => {},
    closeHelpModal: () => {},

    // Close any open modal
    closeAllModals: () => {},
});
