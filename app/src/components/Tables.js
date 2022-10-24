import {Table} from "./Theme";
import {Checkbox, TableBody, TableCell, TableFooter, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import React from "react";

export function SelectableTable({headerContents, selectOn, onSelect, selectedKeys, footer, rows}) {
    footer = footer ? <TableFooter>
        <TableRow>
            {selectOn && <TableHeaderCell/>}
            {footer}
        </TableRow>
    </TableFooter> : null;

    return <Table unstackable striped compact='very'>
        <TableHeader>
            <TableRow>
                {selectOn && <TableHeaderCell/>}
                {headerContents.map(i => <TableHeaderCell key={i}>{i}</TableHeaderCell>)}
            </TableRow>
        </TableHeader>
        <TableBody>
            {rows.map(row =>
                <SelectableRow key={row.key} selectOn={selectOn} onSelect={onSelect} selectedKeys={selectedKeys}>
                    {row}
                </SelectableRow>)}
        </TableBody>
        {footer}
    </Table>
}

function SelectableRow(props) {
    const {selectOn, onSelect, selectedKeys} = props;
    const key = props.children.key;
    const c = selectedKeys && selectedKeys.indexOf(key) >= 0;
    let selectCell;
    if (selectOn) {
        const localOnSelect = (e, {checked}) => {
            try {
                onSelect(key, checked);
            } catch (e) {
                console.error('No onSelect declared');
            }
        };
        selectCell = <TableCell>
            <Checkbox onChange={localOnSelect} checked={c}/>
        </TableCell>;
    }
    return <TableRow key={key}>
        {selectCell}
        {props.children}
    </TableRow>
}
