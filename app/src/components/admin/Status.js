import {Accordion, Header, Progress, Segment, Statistic, StatisticGroup} from "../Theme";
import React, {useContext} from "react";
import {humanBandwidth, humanFileSize, LoadStatistic, useTitle} from "../Common";
import {ProgressPlaceholder} from "../Placeholder";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {Media, SettingsContext, StatusContext, ThemeContext} from "../../contexts/contexts";
import {AccordionContent, AccordionTitle, SegmentGroup} from "semantic-ui-react";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";

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
    // Calculate percent so colors can be shown.
    let percent = (bytes_ps / total) * 100;
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

function DiskBandwidth({name, bytes_read_ps, bytes_write_ps, maximum_read_ps, maximum_write_ps}) {
    const read = <DiskBandwidthProgress
        bytes_ps={bytes_read_ps}
        total={maximum_read_ps}
        label={`${name} read`}
        size='tiny'
        disabled={bytes_read_ps === 0}
    />;
    const write = <DiskBandwidthProgress
        bytes_ps={bytes_write_ps}
        total={maximum_write_ps}
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

function CPUTemperatureStatistic({temperature, high_temperature, critical_temperature, ...props}) {
    if (!temperature) {
        return <Statistic label='Temp C°' value='?'/>
    }
    if ((critical_temperature && temperature >= critical_temperature) || (!critical_temperature && temperature >= 75)) {
        props['color'] = 'red';
    } else if ((high_temperature && temperature >= high_temperature) || (!high_temperature && temperature >= 55)) {
        props['color'] = 'orange';
    }
    return <Statistic label='Temp C°' value={temperature} {...props}/>
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

export function CPUUsageProgress({percent, label}) {
    if (percent === null) {
        return <Progress progress={0} color='grey' label='Average CPU Usage ERROR' disabled/>
    }

    let color = 'black';
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 70) {
        color = 'brown';
    } else if (percent >= 50) {
        color = 'orange';
    }
    return <Progress percent={percent} progress color={color} label={label}/>
}

export function MemoryUsageProgress({percent, label}) {
    if (percent === null) {
        return <Progress progress={0} color='grey' label='RAM Usage' disabled/>
    }

    let color = 'black';
    let size = 'small';
    if (percent >= 90) {
        color = 'red';
        size = 'large';
    } else if (percent >= 70) {
        color = 'orange';
        size = 'large';
    }
    return <Progress percent={percent} progress color={color} label={label} size={size}/>
}


export function StatusPage() {
    useTitle('Status');

    const [activeIndex, setActiveIndex] = React.useState(null);

    const {status} = useContext(StatusContext);
    const {settings} = useContext(SettingsContext);
    const {s} = useContext(ThemeContext);

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
    let memoryPercent;
    let memorySize;

    if (status && status['cpu_info']) {
        const {cpu_info, load, memory_stats} = status;
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

        memoryPercent = Math.round(memory_stats['used'] / memory_stats['total'] * 100);
        memorySize = humanFileSize(memory_stats['total'], 0);
    }

    const SizedHeader = ({children, sizeMobile = 'h1', sizeTablet = 'h2'}) => {
        return <div style={{marginBottom: '1em'}}>
            <Media at='mobile'><Header as={sizeMobile}>{children}</Header></Media>
            <Media greaterThanOrEqual='tablet'><Header as={sizeTablet}>{children}</Header></Media>
        </div>
    }

    const cpuProgress = <CPUUsageProgress percent={percent} label={`CPU Usage (${cores} cores)`}/>;
    const memoryUsageProgress = <MemoryUsageProgress percent={memoryPercent} label={`RAM Usage (${memorySize})`}/>;

    const handleAccordionClick = (e, {index}) => {
        setActiveIndex(activeIndex === index ? -1 : index);
    }

    return <SegmentGroup>
        <Media at='mobile'>
            <Segment>
                {cpuProgress}
                {memoryUsageProgress}
                <StatisticGroup>
                    <CPUTemperatureStatistic
                        temperature={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                    />
                    <LoadStatistic label='1 Minute Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Minute Load' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Minute Load' value={minute_15} cores={cores}/>
                </StatisticGroup>
            </Segment>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Segment>
                {cpuProgress}
                {memoryUsageProgress}
                <StatisticGroup size='mini'>
                    <CPUTemperatureStatistic
                        temperature={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                        style={{marginRight: 0}}
                    />
                    <LoadStatistic label='1 Min. Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Min.' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Min.' value={minute_15} cores={cores}/>
                </StatisticGroup>
            </Segment>
        </Media>

        <Segment>
            <SizedHeader>Drive Bandwidth</SizedHeader>
            {disk_bandwidth && disk_bandwidth.length > 0 ? disk_bandwidth.map((disk) => <DiskBandwidth
                    key={disk['name']} {...disk}/>)
                : <ProgressPlaceholder/>}
        </Segment>

        <Segment>
            <SizedHeader>Network Bandwidth</SizedHeader>
            {bandwidth ? bandwidth.map(i => <BandwidthProgressGroup key={i['name']} bandwidth={i}/>)
                : <ProgressPlaceholder/>}
        </Segment>

        <Segment>
            <SizedHeader>Drive Usage</SizedHeader>
            {drives && drives.length > 0 ? drives.map((drive) => <DriveInfo key={drive['mount']} {...drive}/>)
                : <ProgressPlaceholder/>}
        </Segment>

        <Segment>
            <SizedHeader sizeMobile={'h2'} sizeTablet={'h3'}>Developer</SizedHeader>
            <Accordion>

                <AccordionTitle onClick={handleAccordionClick} index={0}>
                    <Icon name='dropdown'/>
                    Status Details
                </AccordionTitle>
                <AccordionContent active={activeIndex === 0}>
                <pre {...s}>
                    {JSON.stringify(status, undefined, 1)}
                </pre>
                </AccordionContent>

                <AccordionTitle onClick={handleAccordionClick} index={1}>
                    <Icon name='dropdown'/>
                    Settings Details
                </AccordionTitle>
                <AccordionContent active={activeIndex === 1}>
                <pre {...s}>
                    {JSON.stringify(settings, undefined, 1)}
                </pre>
                </AccordionContent>

            </Accordion>
        </Segment>
    </SegmentGroup>
}
