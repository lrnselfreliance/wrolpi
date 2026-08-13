import React from "react";
import _ from "lodash";
import {Table} from "./ui";
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
        let {direction, sortColumn} = this.state;
        rowKey = rowKey || 'key';

        const data = this.props['data'] ? this.sortData(this.props['data']) : null;

        const tableHeader = (spec) => {
            // Under `table-layout: fixed` the header cell is where a column's width is
            // declared; a column that names none divides what is left.  `className` rather
            // than a width so the value can change at a breakpoint.
            const {key, text, sortBy, className} = spec;
            if (sortBy) {
                const active = sortColumn === key;
                return <Table.HeaderCell
                    key={key}
                    className={className}
                    sorted={active ? direction : null}
                    onSort={() => this.changeSort(key)}
                >
                    {text}
                </Table.HeaderCell>;
            } else {
                return <Table.HeaderCell key={key} className={className}>{text}</Table.HeaderCell>
            }
        }

        // Use placeholder while data is null.
        let rows = <Table.Row><Table.Cell colSpan={tableHeaders.length}><TextPlaceholder/></Table.Cell></Table.Row>;
        if (data !== null) {
            if (data.length > 0) {
                // Convert data to table rows.
                rows = data.map(i => <React.Fragment key={i[rowKey]}>{rowFunc(i, this.sortData)}</React.Fragment>);
            } else {
                // No results in data.
                rows = this.props.emptyRow
                    || <Table.Row><Table.Cell colSpan={tableHeaders.length}>No results</Table.Cell></Table.Row>;
            }
        }

        return <Table {...this.props.tableProps}>
            <Table.Header>
                <Table.Row>
                    {tableHeaders.map(tableHeader)}
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {rows}
            </Table.Body>
            {this.props.footer}
        </Table>
    }
}
