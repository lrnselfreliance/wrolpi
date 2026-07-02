import React, {useContext} from 'react';
import {Input, Label, StatisticLabel, StatisticValue} from "semantic-ui-react";
import {Link, Route, Routes} from "react-router";
import {
    ErrorMessage,
    humanFileSize,
    humanNumber,
    mimetypeColor,
    PageContainer,
    toLocaleString,
    useTitle
} from "./Common";
import {ThemeContext} from "../contexts/contexts";
import {Header, Loader, Segment, Statistic} from "./Theme";
import {useStatistics} from "../hooks/customHooks";
import {CalculatorsPage} from "./Calculators";

function StatisticsPage() {
    useTitle('Statistics');

    const {s} = useContext(ThemeContext);

    const {statistics} = useStatistics();

    if (statistics === undefined) {
        return <>
            <Header as='h1'>Statistics</Header>
            <ErrorMessage>Failed to fetch statistics</ErrorMessage>
        </>
    }

    if (statistics['global_statistics']) {
        let {global_statistics, file_statistics} = statistics;
        const {
            archive_count,
            audio_count,
            ebook_count,
            image_count,
            pdf_count,
            total_count,
            video_count,
            zip_count,
            total_size,
            tagged_files,
            tagged_zims,
            tags_count,
        } = file_statistics;
        const {db_size} = global_statistics;
        return <>
            <Header as='h1'>Statistics</Header>
            <Header as='h2'>Files</Header>
            <Segment>
                <Statistic.Group>
                    <Statistic>
                        <StatisticValue>{toLocaleString(total_count)}</StatisticValue>
                        <StatisticLabel>All Files</StatisticLabel>
                    </Statistic>
                    <Statistic>
                        <StatisticValue>{humanFileSize(total_size)}</StatisticValue>
                        <StatisticLabel>Total Size</StatisticLabel>
                    </Statistic>
                </Statistic.Group>
            </Segment>
            <Segment>
                <Statistic.Group size='small'>
                    <Link to={'/videos/statistics'}>
                        <Statistic color={mimetypeColor('video/')}>
                            <StatisticValue>{toLocaleString(video_count)}</StatisticValue>
                            <StatisticLabel>Videos</StatisticLabel>
                        </Statistic>
                    </Link>
                    <Statistic color={mimetypeColor('application/pdf')}>
                        <StatisticValue>{toLocaleString(pdf_count)}</StatisticValue>
                        <StatisticLabel>PDFs</StatisticLabel>
                    </Statistic>
                    <Statistic color={mimetypeColor('application/epub')}>
                        <StatisticValue>{toLocaleString(ebook_count)}</StatisticValue>
                        <StatisticLabel>eBooks</StatisticLabel>
                    </Statistic>
                    <Statistic color={mimetypeColor('text/html')}>
                        <StatisticValue>{toLocaleString(archive_count)}</StatisticValue>
                        <StatisticLabel>Archives</StatisticLabel>
                    </Statistic>
                    <Statistic color={mimetypeColor('image/')}>
                        <StatisticValue>{toLocaleString(image_count)}</StatisticValue>
                        <StatisticLabel>Images</StatisticLabel>
                    </Statistic>
                </Statistic.Group>
            </Segment>
            <Segment>
                <Statistic.Group size='tiny'>
                    <Statistic>
                        <StatisticValue>{toLocaleString(zip_count)}</StatisticValue>
                        <StatisticLabel>ZIP</StatisticLabel>
                    </Statistic>
                    <Statistic color={mimetypeColor('audio/')}>
                        <StatisticValue>{toLocaleString(audio_count)}</StatisticValue>
                        <StatisticLabel>Audio</StatisticLabel>
                    </Statistic>
                </Statistic.Group>
            </Segment>

            <Header as='h2'>Tags</Header>
            <Segment>
                <Statistic.Group>
                    <Statistic>
                        <StatisticValue>{humanNumber(tags_count)}</StatisticValue>
                        <StatisticLabel>Tags</StatisticLabel>
                    </Statistic>
                    <Statistic>
                        <StatisticValue>{humanNumber(tagged_files)}</StatisticValue>
                        <StatisticLabel>Tagged Files</StatisticLabel>
                    </Statistic>
                    <Statistic>
                        <StatisticValue>{humanNumber(tagged_zims)}</StatisticValue>
                        <StatisticLabel>Tagged Zims</StatisticLabel>
                    </Statistic>
                </Statistic.Group>
            </Segment>

            <Header as='h2'>Database</Header>
            <Segment>
                <Statistic.Group>
                    <Statistic>
                        <StatisticValue>{humanFileSize(db_size)}</StatisticValue>
                        <StatisticLabel>Size</StatisticLabel>
                    </Statistic>
                </Statistic.Group>
            </Segment>
        </>;
    }

    return <>
        <Header as='h1'>Statistics</Header>
        <Segment><Loader inline active/></Segment>
    </>;

}

export function MoreRoute(props) {
    return <PageContainer>
        <Routes>
            <Route path='calculators' element={<CalculatorsPage/>}/>
            <Route path='statistics' exact element={<StatisticsPage/>}/>
        </Routes>
    </PageContainer>
}

export function ColoredInput({name, value, label, color, ...props}) {
    label = label ? <Label color={color}>{label}</Label> : null;
    return <Input value={value} name={name} label={label} {...props}/>
}
