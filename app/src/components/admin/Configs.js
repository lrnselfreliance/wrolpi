import {useConfigs} from "../../hooks/customHooks";
import {APIButton, PageContainer} from "../Common";
import {Header, Icon, Table} from "../Theme";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {TableRowPlaceholder} from "../Placeholder";

function WarningIcon({ok}) {
    return <Icon color={ok ? 'violet' : 'red'} name={ok ? 'check' : 'close'}/>
}

function ConfigTableRow({config, importConfig, saveConfig}) {
    const {file_name, valid, successful_import} = config;

    const localImportConfig = async () => {
        await importConfig(file_name);
    }

    const localSaveConfig = async () => {
        await saveConfig(file_name);
    }

    const importButton = <APIButton
        color='grey'
        icon='upload'
        disabled={!valid}
        onClick={localImportConfig}
    />;

    let saveButton;
    if (successful_import) {
        saveButton = <APIButton
            icon='download'
            onClick={localSaveConfig}
        />;
    } else {
        saveButton = <APIButton
            icon='download'
            onClick={localSaveConfig}
            confirmButton='Overwrite'
            confirmContent='Config was not imported successfully, overwrite the config?  Data may be lost!'
        />;
    }

    return <TableRow>
        <TableCell>{file_name}</TableCell>
        <TableCell><WarningIcon ok={successful_import}/></TableCell>
        <TableCell><WarningIcon ok={valid}/></TableCell>
        <TableCell>{importButton}</TableCell>
        <TableCell>{saveButton}</TableCell>
    </TableRow>
}

function ConfigsTable({configs, importConfig, saveConfig}) {
    let body = <TableRow>
        <TableCell colSpan={4}><TableRowPlaceholder/></TableCell>
    </TableRow>

    if (configs === undefined) {
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

export function ConfigsPage() {
    const {configs, importConfig, saveConfig} = useConfigs();

    return <PageContainer>
        <Header as='h1'>Configs</Header>

        <ConfigsTable configs={configs} importConfig={importConfig} saveConfig={saveConfig}/>
    </PageContainer>
}