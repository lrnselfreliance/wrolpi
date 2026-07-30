import React from "react";
import {Button, Header, Modal, Table} from "./ui";
import {SHORTCUTS} from "./KeyboardShortcutsProvider";
import {usePlatformModifier} from "../hooks/customHooks";

// Format keyboard keys for display
function KeyboardKey({children}) {
    return (
        <kbd style={{
            backgroundColor: 'var(--head)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            display: 'inline-block',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.85em',
            lineHeight: '1.4',
            margin: '0 2px',
            padding: '2px 6px',
            whiteSpace: 'nowrap',
        }}>
            {children}
        </kbd>
    );
}

// Parse shortcut keys string and render as keyboard keys
function ShortcutKeys({keys, isMac}) {
    // Handle multiple key combinations (e.g., "meta+k, ctrl+k")
    let combinations = keys.split(', ');

    // Filter to show only platform-appropriate shortcuts when there are multiple combinations
    if (combinations.length > 1) {
        const hasMeta = combinations.some(c => c.toLowerCase().includes('meta'));
        const hasCtrl = combinations.some(c => c.toLowerCase().includes('ctrl'));

        // If we have both meta and ctrl variants, show only the platform-appropriate one
        if (hasMeta && hasCtrl) {
            combinations = combinations.filter(c => {
                const lowerCombo = c.toLowerCase();
                if (isMac) {
                    return lowerCombo.includes('meta');
                } else {
                    return lowerCombo.includes('ctrl');
                }
            });
        }
    }

    return (
        <span>
            {combinations.map((combo, idx) => {
                const parts = combo.split('+').map(part => {
                    // Convert key names to display format
                    switch (part.toLowerCase()) {
                        case 'meta':
                            return 'Cmd';
                        case 'ctrl':
                            return 'Ctrl';
                        case 'shift':
                            return 'Shift';
                        case 'escape':
                            return 'Esc';
                        default:
                            return part.toLowerCase();
                    }
                });

                // Handle sequence shortcuts like "g h"
                const isSequence = combo.includes(' ') && !combo.includes('+');
                if (isSequence) {
                    const seqParts = combo.split(' ');
                    return (
                        <span key={idx}>
                            {idx > 0 && ' / '}
                            {seqParts.map((p, i) => (
                                <React.Fragment key={i}>
                                    <KeyboardKey>{p.toLowerCase()}</KeyboardKey>
                                    {i < seqParts.length - 1 && ' then '}
                                </React.Fragment>
                            ))}
                        </span>
                    );
                }

                return (
                    <span key={idx}>
                        {idx > 0 && ' / '}
                        {parts.map((p, i) => (
                            <React.Fragment key={i}>
                                <KeyboardKey>{p}</KeyboardKey>
                                {i < parts.length - 1 && ' + '}
                            </React.Fragment>
                        ))}
                    </span>
                );
            })}
        </span>
    );
}

// Group shortcuts by category
function groupShortcutsByCategory(shortcuts) {
    const groups = {};
    shortcuts.forEach(shortcut => {
        const category = shortcut.category || 'Other';
        if (!groups[category]) {
            groups[category] = [];
        }
        groups[category].push(shortcut);
    });
    return groups;
}

export default function HelpModal({open, onClose}) {
    const {isMac} = usePlatformModifier();
    const groupedShortcuts = groupShortcutsByCategory(SHORTCUTS);

    // Order categories
    const categoryOrder = ['Search', 'General', 'Help', 'Navigation', 'Page Search', 'Video Player'];
    const orderedCategories = categoryOrder.filter(cat => groupedShortcuts[cat]);

    return (
        <Modal open={open} onClose={onClose} size='small'>
            <Modal.Header>Keyboard Shortcuts</Modal.Header>
            <Modal.Content>
                {orderedCategories.map(category => (
                    <div key={category} style={{marginBottom: '1.5em'}}>
                        <Header as='h4'>{category}</Header>
                        <Table>
                            <Table.Body>
                                {groupedShortcuts[category].map((shortcut, idx) => (
                                    <Table.Row key={idx}>
                                        <Table.Cell width={6}>
                                            <ShortcutKeys keys={shortcut.keys} isMac={isMac}/>
                                        </Table.Cell>
                                        <Table.Cell>{shortcut.description}</Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </div>
                ))}
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={onClose}>Close</Button>
            </Modal.Actions>
        </Modal>
    );
}
