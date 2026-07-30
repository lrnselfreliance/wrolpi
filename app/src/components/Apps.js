import React from 'react';
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
import {Header, Label, Loading, Panel, Statistic, StatisticGroup, TextInput} from "./ui";
import {useStatistics} from "../hooks/customHooks";
import {CalculatorsPage} from "./Calculators";

function StatisticsPage() {
    useTitle('Statistics');

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
            <Panel>
                <StatisticGroup>
                    <Statistic value={toLocaleString(total_count)} label='All Files'/>
                    <Statistic value={humanFileSize(total_size)} label='Total Size'/>
                </StatisticGroup>
            </Panel>
            <Panel>
                <StatisticGroup>
                    <Link to={'/videos/statistics'}>
                        <Statistic color={mimetypeColor('video/')} value={toLocaleString(video_count)}
                                   label='Videos'/>
                    </Link>
                    <Statistic color={mimetypeColor('application/pdf')} value={toLocaleString(pdf_count)}
                               label='PDFs'/>
                    <Statistic color={mimetypeColor('application/epub')} value={toLocaleString(ebook_count)}
                               label='eBooks'/>
                    <Statistic color={mimetypeColor('text/html')} value={toLocaleString(archive_count)}
                               label='Archives'/>
                    <Statistic color={mimetypeColor('image/')} value={toLocaleString(image_count)}
                               label='Images'/>
                </StatisticGroup>
            </Panel>
            <Panel>
                <StatisticGroup>
                    <Statistic value={toLocaleString(zip_count)} label='ZIP'/>
                    <Statistic color={mimetypeColor('audio/')} value={toLocaleString(audio_count)} label='Audio'/>
                </StatisticGroup>
            </Panel>

            <Header as='h2'>Tags</Header>
            <Panel>
                <StatisticGroup>
                    <Statistic value={humanNumber(tags_count)} label='Tags'/>
                    <Statistic value={humanNumber(tagged_files)} label='Tagged Files'/>
                    <Statistic value={humanNumber(tagged_zims)} label='Tagged Zims'/>
                </StatisticGroup>
            </Panel>

            <Header as='h2'>Database</Header>
            <Panel>
                <StatisticGroup>
                    <Statistic value={humanFileSize(db_size)} label='Size'/>
                </StatisticGroup>
            </Panel>
        </>;
    }

    return <>
        <Header as='h1'>Statistics</Header>
        <Panel><Loading/></Panel>
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

/**
 * A text input with a colored tag attached to its leading (or trailing) edge.
 * Replaces Semantic's `<Input label={<Label color={...}/>} labelPosition=.../>`.
 */
export function ColoredInput({name, value, label, color, labelPosition = 'left', fluid, style, ...props}) {
    const labelNode = label ? <Label color={color || 'grey'}>{label}</Label> : null;

    return <div style={{display: 'flex', alignItems: 'stretch', gap: 6, width: fluid ? '100%' : undefined, ...style}}>
        {labelNode && labelPosition === 'left' && labelNode}
        <TextInput name={name} value={value} style={{flex: fluid ? 1 : undefined}} {...props}/>
        {labelNode && labelPosition !== 'left' && labelNode}
    </div>
}
