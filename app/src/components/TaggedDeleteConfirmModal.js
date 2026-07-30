import React from "react";
import {Confirm, Icon, Table} from "./ui";

export function TaggedDeleteConfirmModal({open, taggedFileGroups, onConfirm, onCancel}) {
    return <Confirm
        open={open}
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
