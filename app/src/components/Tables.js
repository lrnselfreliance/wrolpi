import {Checkbox, Table} from "./ui";
import React from "react";

export function SelectableTable({headerContents, selectOn, onSelect, selectedKeys, footer, rows}) {
    footer = footer ? <Table.Footer>
        <Table.Row>
            {footer}
        </Table.Row>
    </Table.Footer> : null;

    return <Table>
        <Table.Header>
            <Table.Row>
                {selectOn && <Table.HeaderCell/>}
                {headerContents.map(i => <Table.HeaderCell key={i}>{i}</Table.HeaderCell>)}
            </Table.Row>
        </Table.Header>
        <Table.Body>
            {rows.map(row =>
                <SelectableRow key={row.key} selectOn={selectOn} onSelect={onSelect} selectedKeys={selectedKeys}>
                    {row}
                </SelectableRow>)}
        </Table.Body>
        {footer}
    </Table>
}

function SelectableRow(props) {
    const {selectOn, onSelect, selectedKeys} = props;
    const key = props.children.key;
    const c = selectedKeys && selectedKeys.indexOf(key) >= 0;
    let selectCell;
    if (selectOn) {
        const localOnSelect = (e) => {
            try {
                onSelect(key, e.currentTarget.checked);
            } catch (e) {
                console.error('No onSelect declared');
            }
        };
        selectCell = <Table.Cell>
            <Checkbox onChange={localOnSelect} checked={c}/>
        </Table.Cell>;
    }
    return <Table.Row key={key}>
        {selectCell}
        {props.children}
    </Table.Row>
}
