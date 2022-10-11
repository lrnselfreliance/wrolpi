import {Header, Loader, Progress, Statistic, StatisticGroup} from "../Theme";
import React from "react";
import {humanBandwidth, humanFileSize, LoadStatistic} from "../Common";
import {getStatus} from "../../api";
import {Container, Divider} from "semantic-ui-react";
import {ProgressPlaceholder} from "../Placeholder";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

function DriveInfo({used, size, percent, mount}) {
    let color;
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 80) {
        color = 'orange';
    }
    return <Progress progress
                     percent={percent}
                     label={`${mount} ${humanFileSize(used)} of ${humanFileSize(size)}`}
                     color={color}
                     key={mount}
    />
}

function CPUTemperatureStatistic({value, high_temperature, critical_temperature}) {
    if (!value) {
        return <Statistic label='Temp C°' value='?'/>
    }
    const props = {};
    if ((critical_temperature && value >= critical_temperature) || (!critical_temperature && value >= 75)) {
        props['color'] = 'red';
    } else if ((high_temperature && value >= high_temperature) || (!high_temperature && value >= 60)) {
        props['color'] = 'orange';
    }
    return <Statistic label='Temp C°' value={value} {...props}/>
}

export function BandwidthProgress({label = '', bytes, maxBytes, ...props}) {
    // Gigabit by default.
    maxBytes = maxBytes || 125_000_000;

    label = `${label} (${humanBandwidth(bytes)})`;
    const percent = (bytes / maxBytes);
    if (percent > 70) {
        props['color'] = 'yellow';
    } else if (percent > 90) {
        props['color'] = 'red';
    }
    return <Progress percent={percent} label={label} {...props}/>
}

export function BandwidthProgressGroup({bandwidth, ...props}) {
    // NIC speed to bytes.
    const maxBytes = bandwidth['speed'] * 125_000;

    const recv = <BandwidthProgress
        bytes={bandwidth['bytes_recv']}
        label={`${bandwidth['name']} In`}
        maxBytes={maxBytes}
        {...props}
    />;

    const sent = <BandwidthProgress
        bytes={bandwidth['bytes_sent']}
        label={`${bandwidth['name']} Out`}
        maxBytes={maxBytes}
        {...props}
    />;

    return <Grid columns={2} stackable>
        <Grid.Row>
            <Grid.Column>
                {recv}
            </Grid.Column>
            <Grid.Column>
                {sent}
            </Grid.Column>
        </Grid.Row>
    </Grid>
}

export function BandwidthProgressCombined({bandwidth, ...props}) {
    const maxBytes = bandwidth['speed'] ? bandwidth['speed'] * 125_000 : 125_000_000;
    const combined = bandwidth['bytes_recv'] + bandwidth['bytes_sent']
    return <BandwidthProgress label={bandwidth['name']} bytes={combined} maxBytes={maxBytes} {...props}/>
}

export function CPUUsageProgress({value, label}) {
    if (value === null) {
        return <Progress progress={0} color='grey' label='Average CPU Usage ERROR' disabled/>
    }

    let color = 'black';
    if (value >= 90) {
        color = 'red';
    } else if (value >= 70) {
        color = 'brown';
    } else if (value >= 50) {
        color = 'orange';
    } else if (value >= 30) {
        color = 'green';
    }
    return <Progress percent={value} progress color={color} label={label}/>
}

export class Status extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: null,
        }
        this.fetchStatus = this.fetchStatus.bind(this);
    }

    async componentDidMount() {
        await this.fetchStatus();
        this.intervalId = setInterval(this.fetchStatus, 1000 * 5);
    }

    componentWillUnmount() {
        clearInterval(this.intervalId);
    }

    fetchStatus = async () => {
        try {
            let status = await getStatus();
            this.setState({status: status});
        } catch (e) {
            console.error(e);
            this.setState({status: null});
        }
    }

    render() {
        if (this.state.status) {
            const {cpu_info, load, drives, bandwidth} = this.state.status;
            const {minute_1, minute_5, minute_15} = load;
            const {percent, cores, temperature, high_temperature, critical_temperature} = cpu_info;

            return <>
                <CPUUsageProgress value={percent} label='CPU Usage'/>

                <CPUTemperatureStatistic
                    value={temperature}
                    high_temperature={high_temperature}
                    critical_temperature={critical_temperature}
                />
                <Statistic label='Cores' value={cores || '?'}/>

                <Divider/>

                <StatisticGroup>
                    <LoadStatistic label='1 Minute Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Minute Load' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Minute Load' value={minute_15} cores={cores}/>
                </StatisticGroup>

                <Divider/>

                <Header as='h1'>Bandwidth</Header>
                {bandwidth ?
                    bandwidth.map(i => <BandwidthProgressGroup key={i['name']} bandwidth={i}/>) :
                    <ProgressPlaceholder/>}

                <Divider/>

                <Header as='h1'>Drive Usage</Header>
                {drives.map((drive) => <DriveInfo key={drive['mount']} {...drive}/>)}
            </>
        }

        return <Container fluid style={{marginBottom: '5em'}}>
            <Loader active inline='centered' size='big'>Loading system status</Loader>
        </Container>
    }
}
