import {
    Accordion,
    Grid,
    Header,
    Panel,
    Progress,
    Statistic,
    StatisticGroup,
    Table,
} from "../ui";
import React, {useContext} from "react";
import {
    Duration,
    humanBandwidth,
    humanFileSize,
    InfoHeader,
    LoadStatistic,
    secondsToHMS,
    secondsToHumanElapsed,
    useTitle
} from "../Common";
import {ProgressPlaceholder} from "../Placeholder";
import {Media, SettingsContext, StatusContext} from "../../contexts/contexts";
import _ from "lodash";

function DriveInfo({used, size, percent, mount}) {
    let color;
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 80) {
        color = 'orange';
    }
    return <Progress
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
    let color = undefined;
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

function DiskBandwidth({name, bytes_read_ps, bytes_write_ps, max_read_ps, max_write_ps}) {
    const read = <DiskBandwidthProgress
        bytes_ps={bytes_read_ps}
        total={max_read_ps}
        label={`${name} read`}
    />;
    const write = <DiskBandwidthProgress
        bytes_ps={bytes_write_ps}
        total={max_write_ps}
        label={`${name} write`}
    />;

    return <Grid>
        <Grid.Col span={6}>{read}</Grid.Col>
        <Grid.Col span={6}>{write}</Grid.Col>
    </Grid>
}

function CPUTemperatureStatistic({temperature, high_temperature, critical_temperature, ...props}) {
    if (!temperature) {
        return <Statistic label='Temp C°' value='?' {...props}/>
    }
    let color;
    if ((critical_temperature && temperature >= critical_temperature) || (!critical_temperature && temperature >= 75)) {
        color = 'red';
    } else if ((high_temperature && temperature >= high_temperature) || (!high_temperature && temperature >= 55)) {
        color = 'orange';
    }
    return <Statistic label='Temp C°' value={temperature} color={color} {...props}/>
}

function FanRPMStatistic({fan_rpm, ...props}) {
    // Only rendered when the device reports a fan (e.g. RPi 5 fan connector).
    if (fan_rpm === null || fan_rpm === undefined) {
        return null;
    }
    return <Statistic label='Fan RPM' value={fan_rpm} {...props}/>
}

function IOWaitStatistic({percent_iowait, ...props}) {
    if (percent_iowait === null || percent_iowait === undefined) {
        return <Statistic label='IO Wait %' value='?' {...props}/>
    }
    let color;
    if (percent_iowait >= 30) {
        color = 'red';
    } else if (percent_iowait >= 10) {
        color = 'orange';
    }
    return <Statistic label='IO Wait %' value={percent_iowait.toFixed(1)} color={color} {...props}/>
}

function formatUptime(seconds) {
    if (!seconds || seconds < 0) return '?';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
        return `${days}d ${hours}h`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

function UptimeStatistic({uptime_seconds, ...props}) {
    const value = formatUptime(uptime_seconds);
    return <Statistic label='Uptime' value={value} {...props}/>
}

export function BandwidthProgress({label = '', bytes, maxBytes, ...props}) {
    // Gigabit by default.
    maxBytes = maxBytes || 125_000_000;

    label = `${label} (${humanBandwidth(bytes)})`;
    const percent = (bytes / maxBytes) * 100;
    let color;
    if (percent > 70) {
        color = 'yellow';
    } else if (percent > 90) {
        color = 'red';
    }
    return <Progress percent={percent} label={label} color={color} {...props}/>
}

export function BandwidthProgressGroup({bandwidth, ...props}) {
    // NIC speed to bytes.
    const maxBytes = bandwidth['speed'] * 1000 * 1000 / 8;

    const recv = <BandwidthProgress
        bytes={bandwidth['bytes_recv_ps']}
        label={`${bandwidth['name']} In`}
        maxBytes={maxBytes}
        {...props}
    />;

    const sent = <BandwidthProgress
        bytes={bandwidth['bytes_sent_ps']}
        label={`${bandwidth['name']} Out`}
        maxBytes={maxBytes}
        {...props}
    />;

    return <Grid>
        <Grid.Col span={6}>{recv}</Grid.Col>
        <Grid.Col span={6}>{sent}</Grid.Col>
    </Grid>
}

export function BandwidthProgressCombined({bandwidth, ...props}) {
    const maxBytes = bandwidth['speed'] ? bandwidth['speed'] * 1000 * 1000 / 8 : 125_000_000;
    const combined = bandwidth['bytes_recv_ps'] + bandwidth['bytes_sent_ps'];
    return <BandwidthProgress label={bandwidth['name']} bytes={combined} maxBytes={maxBytes} {...props}/>
}

export function CPUUsageProgress({percent, label}) {
    if (percent === null) {
        return <Progress percent={0} color='grey' label='Average CPU Usage ERROR'/>
    }

    let color = undefined;
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 70) {
        color = 'brown';
    } else if (percent >= 50) {
        color = 'orange';
    }
    return <Progress percent={percent} color={color} label={label}/>
}

export function MemoryUsageProgress({percent, label}) {
    if (percent === null) {
        return <Progress percent={0} color='grey' label='RAM Usage'/>
    }

    let color = undefined;
    if (percent >= 90) {
        color = 'red';
    } else if (percent >= 70) {
        color = 'orange';
    }
    return <Progress percent={percent} color={color} label={label}/>
}

function ProcessInfoRow({pid, command, percent_cpu, percent_mem}) {
    return <Table.Row failed={percent_cpu >= 80}>
        <Table.Cell className='column-ellipsis'>{command}</Table.Cell>
        <Table.Cell numeric>{percent_cpu}</Table.Cell>
        <Table.Cell numeric>{percent_mem}</Table.Cell>
        <Table.Cell numeric>{pid}</Table.Cell>
    </Table.Row>
}

export function StatusPage() {
    useTitle('Status');

    const {status} = useContext(StatusContext);
    const {settings} = useContext(SettingsContext);

    let percent;
    let cores;
    let temperature;
    let high_temperature;
    let critical_temperature;
    let fan_rpm;
    let processesStats = null;
    let minute_1;
    let minute_5;
    let minute_15;
    let nicBandwidthStats;
    let drivesStats = [];
    let diskBandwidthStats = [];
    let memoryPercent;
    let memorySize;
    let percent_iowait;
    let uptime_seconds;

    if (status && status['cpu_stats']) {
        const {cpu_stats, load_stats, memory_stats, processes_stats, iostat_stats, uptime_stats} = status;
        percent = cpu_stats['percent'];
        cores = cpu_stats['cores'] || '?';
        temperature = cpu_stats['temperature'];
        high_temperature = cpu_stats['high_temperature'];
        critical_temperature = cpu_stats['critical_temperature'];
        fan_rpm = cpu_stats['fan_rpm'];
        processesStats = processes_stats;

        minute_1 = load_stats['minute_1'];
        minute_5 = load_stats['minute_5'];
        minute_15 = load_stats['minute_15'];

        drivesStats = status['drives_stats'];
        nicBandwidthStats = status['nic_bandwidth_stats'];
        diskBandwidthStats = status['disk_bandwidth_stats'];

        memoryPercent = Math.round(memory_stats['used'] / memory_stats['total'] * 100);
        memorySize = humanFileSize(memory_stats['total'], 0);

        // Extract IO wait from iostat stats
        if (iostat_stats) {
            percent_iowait = iostat_stats['percent_iowait'];
        }

        // Extract uptime from uptime stats
        if (uptime_stats) {
            uptime_seconds = uptime_stats['uptime_seconds'];
        }
    }

    const SizedHeader = ({children, sizeMobile = 'h1', sizeTablet = 'h2'}) => {
        return <div style={{marginBottom: '1em'}}>
            <Media at='mobile'><Header as={sizeMobile}>{children}</Header></Media>
            <Media greaterThanOrEqual='tablet'><Header as={sizeTablet}>{children}</Header></Media>
        </div>
    }

    const cpuProgress = <CPUUsageProgress percent={percent} label={`CPU Usage (${cores} cores)`}/>;
    const memoryUsageProgress = <MemoryUsageProgress percent={memoryPercent} label={`RAM Usage (${memorySize})`}/>;

    const noProcessesRow = <Table.Row>
        <Table.Cell colSpan={4}>No top processes</Table.Cell>
    </Table.Row>

    return <>
        <Media at='mobile'>
            <Panel>
                {cpuProgress}
                {memoryUsageProgress}
                <StatisticGroup>
                    <LoadStatistic label='1 Min. Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Min. Load' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Min. Load' value={minute_15} cores={cores}/>
                    <CPUTemperatureStatistic
                        id='cpu_temperature_statistic'
                        temperature={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                    />
                    <FanRPMStatistic fan_rpm={fan_rpm}/>
                    <IOWaitStatistic percent_iowait={percent_iowait}/>
                    <UptimeStatistic uptime_seconds={uptime_seconds}/>
                </StatisticGroup>
            </Panel>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Panel>
                {cpuProgress}
                {memoryUsageProgress}
                <StatisticGroup>
                    <LoadStatistic label='1 Min. Load' value={minute_1} cores={cores}/>
                    <LoadStatistic label='5 Min.' value={minute_5} cores={cores}/>
                    <LoadStatistic label='15 Min.' value={minute_15} cores={cores}/>
                    <CPUTemperatureStatistic
                        id='cpu_temperature_statistic'
                        temperature={temperature}
                        high_temperature={high_temperature}
                        critical_temperature={critical_temperature}
                    />
                    <FanRPMStatistic fan_rpm={fan_rpm}/>
                    <IOWaitStatistic percent_iowait={percent_iowait}/>
                    <UptimeStatistic uptime_seconds={uptime_seconds}/>
                </StatisticGroup>
            </Panel>
        </Media>

        <Panel>
            <InfoHeader
                headerSize='h2'
                headerContent='Drive Bandwidth'
                popupContent='Inaccurate during startup.  Becomes more accurate as the system is used.'
                iconSize='large'
                style={{marginBottom: '1em'}}
            />
            {!_.isEmpty(diskBandwidthStats) ?
                Object.entries(diskBandwidthStats).map(([name, disk]) => <DiskBandwidth key={name} {...disk}/>)
                : <ProgressPlaceholder/>}
        </Panel>

        <Panel>
            <SizedHeader>Network Bandwidth</SizedHeader>
            {!_.isEmpty(nicBandwidthStats) ?
                Object.entries(nicBandwidthStats).map(([name, stats]) => <BandwidthProgressGroup key={name}
                                                                                                 bandwidth={stats}/>)
                : <ProgressPlaceholder/>}
        </Panel>

        <Panel>
            <SizedHeader>Top Processes</SizedHeader>
            <Table className='table-ellipsis'>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>Command</Table.HeaderCell>
                        <Table.HeaderCell>CPU %</Table.HeaderCell>
                        <Table.HeaderCell>Mem %</Table.HeaderCell>
                        <Table.HeaderCell>PID</Table.HeaderCell>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {processesStats && processesStats.length === 0 ?
                        noProcessesRow :
                        processesStats && processesStats.length > 0 ?
                            processesStats.map(i => <ProcessInfoRow key={i.pid} {...i}/>)
                            : <Table.Row><Table.Cell colSpan={4}><ProgressPlaceholder/></Table.Cell></Table.Row>
                    }
                </Table.Body>
            </Table>
        </Panel>

        <Panel>
            <SizedHeader>Drive Usage</SizedHeader>
            {drivesStats && drivesStats.length > 0 ? drivesStats.map((drive) => <DriveInfo
                    key={drive['mount']} {...drive}/>)
                : <ProgressPlaceholder/>}
        </Panel>

        <Panel>
            <SizedHeader sizeMobile={'h2'} sizeTablet={'h3'}>Developer</SizedHeader>
            <Accordion>

                <Accordion.Item value='status'>
                    <Accordion.Control>Status Details</Accordion.Control>
                    <Accordion.Panel>
                        <pre style={{background: 'var(--panel)', color: 'var(--text)', padding: '0.5em'}}>
                            {JSON.stringify(status, undefined, 1)}
                        </pre>
                    </Accordion.Panel>
                </Accordion.Item>

                <Accordion.Item value='settings'>
                    <Accordion.Control>Settings Details</Accordion.Control>
                    <Accordion.Panel>
                        <pre style={{background: 'var(--panel)', color: 'var(--text)', padding: '0.5em'}}>
                            {JSON.stringify(settings, undefined, 1)}
                        </pre>
                    </Accordion.Panel>
                </Accordion.Item>

            </Accordion>
        </Panel>
    </>
}
