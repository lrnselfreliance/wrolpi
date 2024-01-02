import React from "react";
import _ from "lodash";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Table} from "./Theme";
import {TextPlaceholder} from "./Placeholder";

export class SortableTable extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            sortColumn: props.defaultSortColumn || null,
            direction: props.defaultDirection || 'ascending',
        };
    }

    changeSort = (key) => {
        const {sortColumn, direction} = this.state;
        if (key === sortColumn) {
            this.setState({direction: direction === 'ascending' ? 'descending' : 'ascending'});
        } else {
            this.setState({sortColumn: key, direction: 'ascending'});
        }
    }

    sortData = (data) => {
        let {tableHeaders, defaultSortColumn} = this.props;
        let {sortColumn, direction} = this.state;

        const sortKey = sortColumn || defaultSortColumn;
        const sortHeader = _.find(tableHeaders, {key: sortKey});
        if (sortHeader === undefined) {
            // No sort header, probably no default defined.
            return data;
        }
        data = _.sortBy(data, sortHeader['sortBy']);
        data = direction === 'descending' ? data.reverse() : data;
        return data;
    }

    render() {
        let {rowFunc, tableHeaders, rowKey} = this.props;
        let {direction} = this.state;
        rowKey = rowKey || 'key';

        const data = this.props['data'] ? this.sortData(this.props['data']) : null;

        const tableHeader = (spec) => {
            const {key, text, sortBy, width} = spec;
            if (sortBy) {
                return <TableHeaderCell
                    key={key}
                    sorted={this.state['sortColumn'] === key ? direction : null}
                    onClick={() => this.changeSort(key)}
                    width={width || undefined}
                >
                    {text}
                </TableHeaderCell>;
            } else {
                return <TableHeaderCell key={key} width={width}>{text}</TableHeaderCell>
            }
        }

        // Use placeholder while data is null.
        let rows = <TableRow><TableCell colSpan={tableHeaders.length}><TextPlaceholder/></TableCell></TableRow>;
        if (data !== null) {
            if (data.length > 0) {
                // Convert data to table rows.
                rows = data.map(i => <React.Fragment key={i[rowKey]}>{rowFunc(i, this.sortData)}</React.Fragment>);
            } else {
                // No results in data.
                rows = this.props.emptyRow
                    || <TableRow><TableCell colSpan={tableHeaders.length}>No results</TableCell></TableRow>;
            }
        }

        return <Table sortable {...this.props.tableProps}>
            <TableHeader>
                <TableRow>
                    {tableHeaders.map(tableHeader)}
                </TableRow>
            </TableHeader>
            <TableBody>
                {rows}
            </TableBody>
            {this.props.footer}
        </Table>
    }
}
