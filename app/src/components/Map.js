import React, {useContext} from "react";
import {
    APIButton,
    ErrorMessage,
    HandPointMessage,
    InfoPopup,
    humanFileSize,
    IframeViewer,
    InfoMessage,
    PageContainer,
    TabLinks,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Route, Routes} from "react-router-dom";
import {getMapImportStatus, importMapFiles} from "../api";
import {
    Checkbox,
    Divider,
    Icon as SIcon,
    Loader as SLoader,
    PlaceholderLine,
    TableBody,
    TableCell,
    TableFooter,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {Header, Loader, Placeholder, Segment, Table} from "./Theme";
import {StatusContext} from "../contexts/contexts";
import _ from "lodash";
import {MAP_VIEWER_URI} from "./Vars";

function DockerMapImportWarning() {
    const {status} = useContext(StatusContext);
    if (status['dockerized']) {
        return <ErrorMessage storageName='hint_map_docker_warning'>
            <Message.Header>
                Maps are not fully supported in a Docker container!
            </Message.Header>

            <p><b>Only one PBF can be imported and displayed in the docker container.</b></p>

            <p>To import a map file, run the following docker-compose commands:</p>
            <pre>  docker-compose stop map</pre>
            <pre>  docker-compose rm map</pre>
            <pre>  docker-compose run --rm -v /absolute/path/to/map.osm.pbf:/data.osm.pbf
                    -v openstreetmap-data:/var/lib/postgresql/12/main map import
                </pre>

            <p>Be sure to change <b>/absolute/path/to/map.osm.pbf</b>!</p>

            <p>After you have imported a new PBF file, you need to clear the rendered tile cache:</p>
            <pre>  docker volume rm openstreetmap-rendered-tiles</pre>
            <pre>  docker volume create openstreetmap-rendered-tiles</pre>

            <p>Start your map container:</p>
            <pre>  docker-compose up -d map</pre>

            <Divider/>

            <p>You can merge multiple PBF files using osmium (the merged file can then be imported):</p>
            <pre>  osmium merge file1.osm.pbf file2.osm.pbf -o merged.osm.pbf</pre>
        </ErrorMessage>;
    }
    return <></>;
}

function DownloadMessage() {
    return <InfoMessage storageName='hint_map_download'>
        <Message.Header>Where do I get map files?</Message.Header>

        <p>You can download map files from&nbsp;
            <a href='https://download.geofabrik.de/'>https://download.geofabrik.de/</a>
        </p>

        <p><b>Download only the areas you need</b>. Large regions like all of Asia, or the entire
            planet are most likely <b>too large</b> and won't render quickly. It is recommend to only
            import files less than 1GB on a Raspberry Pi.</p>

        <p>Only <b>*.osm.pbf</b> files are supported!</p>

        <p>Place downloaded map files into <b>map/pbf</b> so they can be imported here.</p>
    </InfoMessage>
}

const ViewerMessage = () => {
    return <HandPointMessage>
        <p>You can view your Map at <a href={MAP_VIEWER_URI}>{MAP_VIEWER_URI}</a></p>
    </HandPointMessage>
}

function SlowImportMessage() {
    const {status} = useContext(StatusContext);
    if (status && status['cpu_stats'] && status['cpu_stats']['temperature'] >= 80) {
        return <Message warning icon>
            <SIcon name='exclamation'/>
            <Message.Content>
                <Message.Header>
                    CPU temperature is too high
                </Message.Header>
                <p>Any import may take much more time because the CPU is throttled.</p>
                <small>If your import takes more time than estimated, you will need an aftermarket cooler.</small>
            </Message.Content>
        </Message>
    }
    return <></>
}

class ManageMap extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            files: null,
            pending: null,
            import_running: false,
            selectedPaths: [],
            dockerized: null,
        }
    }

    async componentDidMount() {
        await this.fetchImportStatus();
        this.intervalId = setInterval(this.fetchImportStatus, 1000 * 30);
    }

    componentWillUnmount() {
        clearInterval(this.intervalId);
    }

    fetchImportStatus = async () => {
        try {
            const importStatus = await getMapImportStatus();
            this.setState({
                files: importStatus['files'],
                pending: importStatus['pending'],
                import_running: importStatus['import_running'],
                dockerized: importStatus['dockerized'],
            });
        } catch (e) {
            console.error(e);
            this.setState({files: undefined});
        }
    }

    import = async (e) => {
        if (e) {
            e.preventDefault();
        }

        this.setState({'ready': false});
        const {files, selectedPaths} = this.state;
        if (_.isEmpty(selectedPaths)) {
            // No files are selected, import all.
            let paths = [];
            for (let i = 0; i < files.length; i++) {
                paths = paths.concat([files[i].path]);
            }
            await importMapFiles(paths);
        } else {
            await importMapFiles(selectedPaths);
        }
        await this.fetchImportStatus();
    }

    handleCheckbox = (checked, pbf) => {
        let {selectedPaths} = this.state;
        if (checked === true) {
            selectedPaths = selectedPaths.concat([pbf.path]);
        } else {
            const index = selectedPaths.indexOf(pbf.path);
            if (index > -1) {
                selectedPaths.splice(index, 1);
            }
        }
        this.setState({selectedPaths});
    }

    tableRow = (pbf, disabled) => {
        let ref = React.createRef();
        const {size, path, imported, time_to_import} = pbf;
        let sizeCells = (<>
            <TableCell>{humanFileSize(size)}</TableCell>
            <TableCell>{humanFileSize(size * 25)}</TableCell>
            <TableCell>{time_to_import}</TableCell>
        </>);
        return <TableRow key={path}>
            <TableCell collapsing>
                <Checkbox
                    disabled={disabled}
                    ref={ref}
                    onChange={(e, data) => this.handleCheckbox(data.checked, pbf)}
                />
            </TableCell>
            <TableCell>
                <a href={`/media/${path}`}>{path}</a>
            </TableCell>
            <TableCell>
                {this.state.pending && this.state.pending.indexOf(path) >= 0 ?
                    <SLoader active inline size='mini'/> :
                    imported ? 'yes' : 'no'}
            </TableCell>
            {size !== null ? sizeCells : <TableCell colSpan={3}/>}
        </TableRow>
    }

    render() {
        const {files, selectedPaths, import_running, pending, dockerized} = this.state;

        const importingMessage = pending ?
            pending.length > 1 ? 'Importing...' : `Importing ${pending[0]}`
            : null;

        let disabled = dockerized || _.isEmpty(files) || import_running;
        let importButton = <APIButton
            color='violet'
            disabled={disabled}
            onClick={this.import}
        >
            {!_.isEmpty(selectedPaths) ? 'Import Selected' : 'Import All'}
        </APIButton>;

        let rows = <TableRow>
            <TableCell/>
            <TableCell colSpan={6}>
                <Placeholder>
                    <PlaceholderLine/>
                    <PlaceholderLine/>
                </Placeholder>
            </TableCell>
        </TableRow>;
        if (files && files.length === 0) {
            rows = <TableRow>
                <TableCell/><TableCell colSpan={5}>No PBF map files were found in <b>map/pbf</b></TableCell>
            </TableRow>;
        } else if (files && files.length >= 1) {
            rows = files.map(i => this.tableRow(i, disabled));
        } else if (files === undefined) {
            rows = <TableRow>
                <TableCell colSpan={6}>
                    <ErrorMessage>Could not fetch map files</ErrorMessage>
                </TableCell>
            </TableRow>
        }

        let spaceInfoPopup = <InfoPopup
            content='Upon importing, a PBF file will consume more disk space than the original file.'/>;
        let timeInfoPopup = <InfoPopup content='Estimated for a Raspberry Pi 4'/>;

        return <PageContainer>
            <WROLModeMessage content='Cannot modify Map'/>
            <DockerMapImportWarning/>
            <SlowImportMessage/>
            <Loader size='large' active={import_running} inline='centered'>
                {importingMessage}
            </Loader>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell/>
                        <TableHeaderCell>PBF File</TableHeaderCell>
                        <TableHeaderCell>Imported</TableHeaderCell>
                        <TableHeaderCell>Size</TableHeaderCell>
                        <TableHeaderCell>Space Required {spaceInfoPopup}</TableHeaderCell>
                        <TableHeaderCell>Time to Import {timeInfoPopup}</TableHeaderCell>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {rows}
                </TableBody>
                <TableFooter>
                    <TableRow>
                        <TableHeaderCell/>
                        <TableHeaderCell colSpan={5}>
                            {importButton}
                        </TableHeaderCell>
                    </TableRow>
                </TableFooter>
            </Table>
            <DownloadMessage/>
            <ViewerMessage/>
        </PageContainer>
    }
}

function MapPage() {
    const fallback = <Segment>
        <Header as='h3'>Failed to fetch Map service.</Header>
        <p>You may need to give permission to access the page: <a href={MAP_VIEWER_URI}>{MAP_VIEWER_URI}</a></p>

        <p>Map startup is delayed on boot, if you have just started your WROLPi try again in a few minutes.</p>

        <p>If the above does not work, try starting the service:</p>
        <pre>sudo systemctl start renderd</pre>
        <pre>sudo systemctl start apache2</pre>

        <p>Check the logs</p>
        <pre>journalctl -u renderd</pre>
        <pre>sudo tail -f /var/log/apache2/*log</pre>
    </Segment>;

    return <IframeViewer title='map' src={MAP_VIEWER_URI} fallback={fallback}/>
}

export function MapRoute() {
    useTitle('Map');

    const links = [
        {text: 'Map', to: '/map', key: 'map', end: true},
        {text: 'Manage', to: '/map/manage', key: 'manage'},
    ];

    return <div style={{marginTop: '2em'}}>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<MapPage/>}/>
            <Route path='manage' exact element={<ManageMap/>}/>
        </Routes>
    </div>
}
