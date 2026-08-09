import React from "react";
import {Button, Group, Header, Panel, Select, Text} from "../ui";
import {downloadCSV, inventoryExportFilename, toCSV} from "./inventoryExport";
import {groupFieldsOf, summableFieldsOf} from "./summarize";

const fieldOptions = (fs) => fs.map(f => ({value: f.key, label: f.label}));

/**
 * The "Export" tab: explains each export format and provides the action to produce it.  CSV is the raw items table,
 * generated entirely in the browser.  "PDF" opens the print dialog over the hidden printable view (see
 * InventoryPrint), which includes a summary table grouped by the field chosen here.
 */
export function InventoryExportPanel({name, fields, items, groupKey, sumKey, onGroupKey, onSumKey}) {
    const count = (items || []).length;
    const groupFields = groupFieldsOf(fields);
    const summableFields = summableFieldsOf(fields);

    const exportCSV = () =>
        downloadCSV(inventoryExportFilename(name, 'csv'), toCSV(fields, items));

    return <>
        <Panel>
            <Header as='h3' icon='file alternate outline'>CSV</Header>
            <Text>
                A comma-separated spreadsheet of all {count} item{count === 1 ? '' : 's'} and every field, openable
                in Excel, Numbers, or Google Sheets.  Generated entirely on this device.
            </Text>
            <Button role='primary' onClick={exportCSV} disabled={count === 0} icon='download'>
                Download CSV
            </Button>
        </Panel>

        <Panel>
            <Header as='h3' icon='file pdf outline'>PDF</Header>
            <Text>
                A printable table of the whole inventory, followed by a summary grouped by the field you choose.
                This opens your browser's print dialog — choose "Save as PDF" as the destination to get a PDF file,
                or print it on paper.
            </Text>
            {groupFields.length > 0 &&
                <Group mb='1em' gap='1em' wrap='wrap'>
                    <span>
                        Summary group:{' '}
                        <Select data={fieldOptions(groupFields)} value={groupKey || ''}
                                onChange={value => onGroupKey(value)}/>
                    </span>
                    {summableFields.length > 0 &&
                        <span>
                            Sum:{' '}
                            <Select clearable data={fieldOptions(summableFields)} value={sumKey || ''}
                                    onChange={value => onSumKey(value || undefined)}/>
                        </span>}
                </Group>}
            <Button onClick={() => window.print()} disabled={count === 0} icon='print'>
                Print / Save as PDF
            </Button>
        </Panel>
    </>;
}
