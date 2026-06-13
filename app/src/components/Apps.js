import React, {useContext, useState} from 'react';
import {
    Divider,
    Input,
    Label,
    SegmentGroup,
    StatisticLabel,
    StatisticValue,
    TableCell,
    TableRow
} from "semantic-ui-react";
import {Link, Route, Routes} from "react-router";
import {decryptOTP, encryptOTP, generateHtml} from "./otp";
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
import {Button, Header, Loader, Segment, Statistic, Table, TextArea} from "./Theme";
import {useStatistics, useVINDecoder} from "../hooks/customHooks";
import {CalculatorsPage} from "./Calculators";

function Encrypt() {
    // Encrypt happens live as the user types or pastes.  Nothing leaves the browser.
    const [otp, setOtp] = useState('');
    const [plaintext, setPlaintext] = useState('');

    const handleInputChange = (event, {name, value}) => {
        if (name === 'otp') {
            setOtp(value);
        } else {
            setPlaintext(value);
        }
    };

    let ciphertext = '';
    let error = '';
    if (otp && plaintext) {
        try {
            ciphertext = encryptOTP(otp, plaintext).ciphertext;
        } catch (e) {
            error = e.message;
        }
    }

    return <>
        <Header as='h2'>Encrypt</Header>
        <SegmentGroup>
            <Segment>
                <h3>Key</h3>
                <TextArea
                    name='otp'
                    className='otp'
                    value={otp}
                    onChange={handleInputChange}
                    placeholder='The random letters from your One-Time Pad'
                />
            </Segment>
            <Segment>
                <h3>Plaintext</h3>
                <TextArea
                    name='plaintext'
                    className='otp'
                    value={plaintext}
                    onChange={handleInputChange}
                    placeholder='The message you want to send'
                />
            </Segment>
            <Segment>
                <h3>Ciphertext</h3>
                {error
                    ? <ErrorMessage>{error}</ErrorMessage>
                    : <pre>{ciphertext || 'Enter your message above'}</pre>}
            </Segment>
        </SegmentGroup>
    </>
}

function Decrypt() {
    // Decrypt happens live as the user types or pastes.  Nothing leaves the browser.
    const [otp, setOtp] = useState('');
    const [ciphertext, setCiphertext] = useState('');

    const handleInputChange = (event, {name, value}) => {
        if (name === 'otp') {
            setOtp(value);
        } else {
            setCiphertext(value);
        }
    };

    let plaintext = '';
    let error = '';
    if (otp && ciphertext) {
        try {
            plaintext = decryptOTP(otp, ciphertext).plaintext;
        } catch (e) {
            error = e.message;
        }
    }

    return <>
        <Header as='h2'>Decrypt</Header>
        <SegmentGroup>
            <Segment>
                <h3>Key</h3>
                <TextArea
                    name='otp'
                    className='otp'
                    value={otp}
                    onChange={handleInputChange}
                    placeholder='The random letters from your One-Time Pad'
                />
            </Segment>
            <Segment>
                <h3>Ciphertext</h3>
                <TextArea
                    name='ciphertext'
                    className='otp'
                    value={ciphertext}
                    onChange={handleInputChange}
                    placeholder='The message you received'
                />
            </Segment>
            <Segment>
                <h3>Plaintext</h3>
                {error
                    ? <ErrorMessage>{error}</ErrorMessage>
                    : <pre>{plaintext || 'Enter the encrypted message above'}</pre>}
            </Segment>
        </SegmentGroup>
    </>
}

function OTP() {
    useTitle('One Time Pad');

    const {t} = useContext(ThemeContext);

    let cheatSheetURL = `${process.env.PUBLIC_URL}/one-time-pad-cheat-sheet.pdf`;

    // Generate a new One-Time Pad entirely in the browser and open it in a new tab so it can be printed.  The pad is
    // never sent to or stored on the server.
    const handleGenerateNewPad = () => {
        const blob = new Blob([generateHtml()], {type: 'text/html'});
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
    };

    return <>
        <Header as='h1'>One-Time Pad</Header>
        <Header as='h4'>One-Time Pads can be used to encrypt your communications. This can be done by hand
            (yes, really) or in this app.</Header>
        <p {...t}>These messages are never stored and cannot be retrieved.</p>
        <Button color='violet' onClick={handleGenerateNewPad}>Generate New Pad</Button>
        <Button secondary href={cheatSheetURL}>Cheat Sheet PDF</Button>

        <Divider/>
        <Encrypt/>

        <Divider/>
        <Decrypt/>
    </>
}

function VINDecoder() {
    useTitle('VIN Number Decoder');
    const {t} = useContext(ThemeContext);

    const basicKeys = ['Country', 'Manufacturer', 'Region', 'Years'];
    const detailsKeys = ['Body', 'Engine', 'Model', 'Plant', 'Transmission', 'Serial'];

    const {value, setValue, vin} = useVINDecoder();
    console.debug(vin);

    let body = <p {...t}>Enter a VIN number above</p>;
    if (value && !vin) {
        body = <p {...t}>VIN number is invalid</p>;
    }
    if (vin && vin['country']) {
        let details = <p {...t}>No details</p>;
        if (vin['body']) {
            details = <Table celled columns={2} {...t}>
                {detailsKeys.map(i => <TableRow key={i}>
                    <TableCell width={5}><b>{i}</b></TableCell>
                    <TableCell width={11}>{vin[i.toLowerCase()] || '(Unknown)'}</TableCell>
                </TableRow>)}
            </Table>;
        }
        body = <>
            <Table celled columns={2} {...t}>
                {basicKeys.map(i => <TableRow key={i}>
                    <TableCell width={5}><b>{i}</b></TableCell>
                    <TableCell width={11}>{vin[i.toLowerCase()]}</TableCell>
                </TableRow>)}
            </Table>
            <Header as='h3'>Details</Header>
            {details}
        </>;
    }

    return <>
        <Header as='h1'>VIN Number Decoder</Header>
        <Input
            size='large'
            label='VIN'
            value={value}
            onChange={e => setValue(e.target.value)}
        />

        <Header as='h2'>Decoded</Header>
        {body}
    </>
}


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
            <Route path='otp' exact element={<OTP/>}/>
            <Route path='statistics' exact element={<StatisticsPage/>}/>
            <Route path='vin' exact element={<VINDecoder/>}/>
        </Routes>
    </PageContainer>
}

export function ColoredInput({name, value, label, color, ...props}) {
    label = label ? <Label color={color}>{label}</Label> : null;
    return <Input value={value} name={name} label={label} {...props}/>
}