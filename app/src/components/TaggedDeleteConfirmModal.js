import React from "react";
import {Confirm, Icon, Table} from "./ui";

export function TaggedDeleteConfirmModal({open, taggedFileGroups, onConfirm, onCancel}) {
    return <Confirm
        open={open}
        /*
         * Audited: `large` (620px).  The only confirmation that is not a one-line question --
         * it lists file paths beside their tags, and `videos/Practical Engineering/Season
         * 2024/` alone is 40 characters before the filename.  The table scrolls sideways in
         * its own container, so the width decides how much of a path is readable at a glance;
         * at Confirm's default 380px that was the first two directories.
         */
        size='large'
        title={<><Icon name='warning sign'/> Tagged Files Will Be Deleted</>}
        confirmLabel='Delete'
        destructive
        onConfirm={onConfirm}
        onCancel={onCancel}
    >
        <p>The following tagged files will be deleted:</p>
        <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>File</Table.HeaderCell>
                    <Table.HeaderCell>Tags</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {(taggedFileGroups || []).map((fg, idx) => (
                    <Table.Row key={fg.id ?? idx}>
                        <Table.Cell>{fg.primary_path || fg.name}</Table.Cell>
                        <Table.Cell>{(fg.tags || []).join(', ')}</Table.Cell>
                    </Table.Row>
                ))}
            </Table.Body>
        </Table>
    </Confirm>;
}
