import React from "react";
import {Button, Icon, Modal, Table} from "./Theme";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";

export function TaggedDeleteConfirmModal({open, taggedFileGroups, onConfirm, onCancel}) {
    return <Modal open={open} onClose={onCancel} closeIcon>
        <Modal.Header><Icon name='warning sign'/> Tagged Files Will Be Deleted</Modal.Header>
        <Modal.Content>
            <p>The following tagged files will be deleted:</p>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>File</TableHeaderCell>
                        <TableHeaderCell>Tags</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {(taggedFileGroups || []).map((fg, idx) => (
                        <TableRow key={fg.id ?? idx}>
                            <TableCell>{fg.primary_path || fg.name}</TableCell>
                            <TableCell>{(fg.tags || []).join(', ')}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onCancel}>Cancel</Button>
            <Button color='red' onClick={onConfirm}>
                <Icon name='trash'/> Delete
            </Button>
        </Modal.Actions>
    </Modal>;
}
