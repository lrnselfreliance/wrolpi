import React from "react";
import {Select} from "semantic-ui-react";
import {Button, Header, Icon, Segment} from "../Theme";
import {downloadCSV, inventoryExportFilename, toCSV} from "./inventoryExport";
import {groupFieldsOf, summableFieldsOf} from "./summarize";
import {ThemeContext} from "../../contexts/contexts";

const fieldOptions = (fs) => fs.map(f => ({key: f.key, value: f.key, text: f.label}));

/**
 * The "Export" tab: explains each export format and provides the action to produce it.  CSV is the raw items table,
 * generated entirely in the browser.  "PDF" opens the print dialog over the hidden printable view (see
 * InventoryPrint), which includes a summary table grouped by the field chosen here.
 */
export function InventoryExportPanel({name, fields, items, groupKey, sumKey, onGroupKey, onSumKey}) {
    const count = (items || []).length;
    const groupFields = groupFieldsOf(fields);
    const summableFields = summableFieldsOf(fields);
    const {t} = React.useContext(ThemeContext);

    const exportCSV = () =>
        downloadCSV(inventoryExportFilename(name, 'csv'), toCSV(fields, items));

    return <>
        <Segment>
            <Header as='h3'><Icon name='file alternate outline'/> CSV</Header>
            <p {...t}>
                A comma-separated spreadsheet of all {count} item{count === 1 ? '' : 's'} and every field, openable
                in Excel, Numbers, or Google Sheets.  Generated entirely on this device.
            </p>
            <Button primary onClick={exportCSV} disabled={count === 0}>
                <Icon name='download'/> Download CSV
            </Button>
        </Segment>

        <Segment>
            <Header as='h3'><Icon name='file pdf outline'/> PDF</Header>
            <p {...t}>
                A printable table of the whole inventory, followed by a summary grouped by the field you choose.
                This opens your browser's print dialog — choose "Save as PDF" as the destination to get a PDF file,
                or print it on paper.
            </p>
            {groupFields.length > 0 &&
                <div style={{marginBottom: '1em', display: 'flex', gap: '1em', flexWrap: 'wrap'}}>
                    <span>
                        Summary group:{' '}
                        <Select options={fieldOptions(groupFields)} value={groupKey || ''}
                                onChange={(e, data) => onGroupKey(data.value)}/>
                    </span>
                    {summableFields.length > 0 &&
                        <span>
                            Sum:{' '}
                            <Select clearable options={fieldOptions(summableFields)} value={sumKey || ''}
                                    onChange={(e, data) => onSumKey(data.value || undefined)}/>
                        </span>}
                </div>}
            <Button onClick={() => window.print()} disabled={count === 0}>
                <Icon name='print'/> Print / Save as PDF
            </Button>
        </Segment>
    </>;
}
