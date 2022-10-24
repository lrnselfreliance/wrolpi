import {Table} from "./Theme";
import {Checkbox, TableBody, TableCell, TableFooter, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import React from "react";

export function SelectableTable({headerContents, selectOn, onSelect, footer, rows}) {
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
                <SelectableRow key={row.key} selectOn={selectOn} onSelect={onSelect}>{row}</SelectableRow>)}
        </TableBody>
        {footer}
    </Table>
}

function SelectableRow(props) {
    const {selectOn, onSelect} = props;
    let selectCell;
    if (selectOn) {
        const localOnSelect = (e, {checked}) => {
            try {
                onSelect(props.children.key, checked);
            } catch (e) {
                console.error('No onSelect declared');
            }
        };
        selectCell = <TableCell>
            <Checkbox onChange={localOnSelect}/>
        </TableCell>;
    }
    return <TableRow key={props.children.key}>
        {selectCell}
        {props.children}
    </TableRow>
}
