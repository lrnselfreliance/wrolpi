import {useConfigs} from "../../hooks/customHooks";
import {APIButton, PageContainer} from "../Common";
import {Header, Icon, Popup, Table} from "../Theme";
import React from "react";
import {
    Grid,
    GridColumn,
    GridRow,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import {TableRowPlaceholder} from "../Placeholder";
import {useNavigate} from "react-router-dom";

function WarningIcon({ok}) {
    return <Icon color={ok ? 'violet' : 'red'} name={ok ? 'check' : 'close'}/>
}

function ConfigTableRow({config, importConfig, saveConfig, fetchConfigs}) {
    const {file_name, rel_path, valid, successful_import} = config;
    const navigate = useNavigate();

    const localImportConfig = async () => {
        await importConfig(file_name);
        await fetchConfigs();
    }

    const localSaveConfig = async () => {
        await saveConfig(file_name);
        await fetchConfigs();
    }

    const importButton = <APIButton
        icon='upload'
        disabled={!valid}
        onClick={localImportConfig}
    />;

    let saveButton;
    if (successful_import) {
        saveButton = <APIButton
            color='grey'
            icon='download'
            onClick={localSaveConfig}
        />;
    } else {
        // Warn the user they may overwrite because import was not successful.
        saveButton = <APIButton
            color='grey'
            icon='download'
            onClick={localSaveConfig}
            confirmButton='Overwrite'
            confirmContent='Config was not imported successfully, overwrite the config?  Data may be lost!'
        />;
    }

    return <TableRow>
        <TableCell><span onClick={() => navigate(`?preview=${rel_path}`)}>{file_name}</span></TableCell>
        <TableCell><WarningIcon ok={successful_import}/></TableCell>
        <TableCell><WarningIcon ok={valid}/></TableCell>
        <TableCell>{importButton}</TableCell>
        <TableCell>{saveButton}</TableCell>
    </TableRow>
}

export function ConfigsTable({configs, loading, importConfig, saveConfig, fetchConfigs}) {
    let body = <TableRow>
        <TableCell colSpan={4}><TableRowPlaceholder/></TableCell>
    </TableRow>

    if (loading) {
        // Configs are being fetched again.
    } else if (configs === undefined) {
        body = <TableRow>
            <TableCell colSpan={2}>Failed to fetch configs</TableCell>
        </TableRow>;
    } else if (configs && Object.keys(configs).length === 0) {
        body = <TableRow>
            <TableCell colSpan={2}>No configs exist. Try tagging some files.</TableCell>
        </TableRow>;
    } else if (configs) {
        body = Object.entries(configs).map(([key, value]) =>
            <ConfigTableRow
                key={key}
                config={value}
                importConfig={importConfig}
                saveConfig={saveConfig}
                fetchConfigs={fetchConfigs}
            />
        );
    }

    return <Table unstackable striped>
        <TableHeader>
            <TableRow>
                <TableHeaderCell width={10}>File Name</TableHeaderCell>
                <TableHeaderCell width={1}>Imported</TableHeaderCell>
                <TableHeaderCell width={1}>Valid</TableHeaderCell>
                <TableHeaderCell width={1}>Import</TableHeaderCell>
                <TableHeaderCell width={1}>Save</TableHeaderCell>
            </TableRow>
        </TableHeader>

        <TableBody>
            {body}
        </TableBody>
    </Table>
}