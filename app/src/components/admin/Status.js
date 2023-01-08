import {Header, Progress, Segment, Statistic, StatisticGroup} from "../Theme";
import React, {useContext} from "react";
import {humanBandwidth, humanFileSize, LoadStatistic, useTitle} from "../Common";
import {ProgressPlaceholder} from "../Placeholder";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Media, StatusContext} from "../../contexts/contexts";

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

function DiskBandwidthProgress({bytes_ps, total, label, ...props}) {
    let percent = bytes_ps / total;
    percent = percent || 0;
    let color = null;
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 80) {
        color = 'orange';
    } else if (percent >= 50) {
        color = 'yellow';
    }
    label = `${label} ${humanBandwidth(bytes_ps)}`;
    return <Progress percent={percent} label={label} color={color} key={label} {...props}/>;
}

function DiskBandwidth({name, bytes_read_ps, bytes_write_ps}) {
    const total = 10_000_000; // Arbitrary size.  What is the real speed of the disk?

    const read = <DiskBandwidthProgress
        bytes_ps={bytes_read_ps}
        total={total}
        label={`${name} read`}
        size='tiny'
        disabled={bytes_read_ps === 0}
    />;
    const write = <DiskBandwidthProgress
        bytes_ps={bytes_write_ps}
        total={total}
        label={`${name} write`}
        size='tiny'
        disabled={bytes_write_ps === 0}
    />;

    return <Grid columns={2}>
        <Grid.Row>
            <Grid.Column>{read}</Grid.Column>
            <Grid.Column>{write}</Grid.Column>
        </Grid.Row>
    </Grid>
}

function CPUTemperatureStatistic({value, high_temperature, critical_temperature, ...props}) {
    if (!value) {
        return <Statistic label='Temp C°' value='?'/>
    }
    if (critical_temperature && critical_temperature === high_temperature) {
        // Critical and high are equal, manually change it so high changes color before critical.
        high_temperature = critical_temperature - 25;
    }
    if ((critical_temperature && value >= critical_temperature) || (!critical_temperature && value >= 75)) {
        props['color'] = 'red';
    } else if ((high_temperature && value >= high_temperature) || (!high_temperature && value >= 55)) {
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
    const disabled = percent === 0;
    return <Progress percent={percent} label={label} disabled={disabled} {...props}/>
}

export function BandwidthProgressGroup({bandwidth, ...props}) {
    // NIC speed to bytes.
    const maxBytes = bandwidth['speed'] * 125_000;

    const recv = <BandwidthProgress
        bytes={bandwidth['bytes_recv']}
        label={`${bandwidth['name']} In`}
        maxBytes={maxBytes}
        size='small'
        {...props}
    />;

    const sent = <BandwidthProgress
        bytes={bandwidth['bytes_sent']}
        label={`${bandwidth['name']} Out`}
        maxBytes={maxBytes}
        size='small'
        {...props}
    />;

    return <Grid columns={2}>
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
    }
    return <Progress percent={value} progress color={color} label={label}/>
}

export function Status() {
    useTitle('Status');

    const {status} = useContext(StatusContext);

    let percent;
    let cores;
    let temperature;
    let high_temperature;
    let critical_temperature;
    let minute_1;
    let minute_5;
    let minute_15;
    let bandwidth;
    let drives = [];
    let disk_bandwidth = [];

    if (status && status['cpu_info']) {
        const {cpu_info, load} = status;
        percent = cpu_info['percent'];
        cores = cpu_info['cores'];
        temperature = cpu_info['temperature'];
        high_temperature = cpu_info['high_temperature'];
        critical_temperature = cpu_info['critical_temperature'];

        minute_1 = load['minute_1'];
        minute_5 = load['minute_5'];
        minute_15 = load['minute_15'];

        drives = status['drives'];
        bandwidth = status['bandwidth'];
        disk_bandwidth = status['disk_bandwidth'];
    }

    return <>
        <Media at='mobile'>
            <Segment>
                <CPUUsageProgress value={percent} label='CPU Usage'/>
                <StatisticGroup>
                    <CPUTemperatureStatistic
                        value={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                    />
                    <LoadStatistic label='1 Minute Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Minute Load' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Minute Load' value={minute_15} cores={cores}/>
                </StatisticGroup>
            </Segment>

            <Segment>
                <Header as='h1'>Network Bandwidth</Header>
                {bandwidth ? bandwidth.map(i => <BandwidthProgressGroup key={i['name']} bandwidth={i}/>) :
                    <ProgressPlaceholder/>}
            </Segment>

            <Segment>
                <Header as='h1'>Drive Usage</Header>
                {drives.map((drive) => <DriveInfo key={drive['mount']} {...drive}/>)}
            </Segment>

            <Segment>
                <Header as='h1'>Drive Bandwidth</Header>
                {disk_bandwidth.map((disk) => <DiskBandwidth key={disk['name']} {...disk}/>)}
            </Segment>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Segment>
                <CPUUsageProgress value={percent} label='CPU Usage'/>
                <StatisticGroup size='mini'>
                    <CPUTemperatureStatistic
                        value={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                        style={{marginRight: 0}}
                    />
                    <LoadStatistic label='1 Min. Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Min.' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Min.' value={minute_15} cores={cores}/>
                </StatisticGroup>
            </Segment>

            <Segment>
                <Header as='h2'>Network Bandwidth</Header>
                {bandwidth ? bandwidth.map(i => <BandwidthProgressGroup key={i['name']} bandwidth={i}/>) :
                    <ProgressPlaceholder/>}
            </Segment>

            <Segment>
                <Header as='h2'>Drive Usage</Header>
                {drives.map((drive) => <DriveInfo key={drive['mount']} {...drive}/>)}
            </Segment>

            <Segment>
                <Header as='h2'>Drive Bandwidth</Header>
                {disk_bandwidth.map((disk) => <DiskBandwidth key={disk['name']} {...disk}/>)}
            </Segment>
        </Media>
    </>
}
