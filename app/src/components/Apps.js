import React, {useContext} from 'react';
import {Divider, SegmentGroup, StatisticLabel, StatisticValue} from "semantic-ui-react";
import {Link, Route, Routes} from "react-router-dom";
import {decryptOTP, encryptOTP} from "../api";
import {humanFileSize, mimetypeColor, PageContainer, toLocaleString, useTitle} from "./Common";
import {ThemeContext} from "../contexts/contexts";
import {Button, Header, Loader, Segment, Statistic, StatisticGroup, TextArea} from "./Theme";
import {useStatistics} from "../hooks/customHooks";

class Encrypt extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            otp: '', plaintext: '', ciphertext: '',
        }
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        try {
            let {otp, plaintext, ciphertext} = await encryptOTP(this.state.otp, this.state.plaintext);
            this.setState({otp, plaintext, ciphertext});
        } catch (e) {
            console.error(e);
        }
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value});
    }

    render() {
        return <>
            <Header as='h2'>Encrypt</Header>
            <SegmentGroup>
                <Segment>
                    <h3>Key</h3>
                    <TextArea
                        name='otp'
                        className='otp'
                        value={this.state.otp}
                        onChange={this.handleInputChange}
                        placeholder='The random letters from your One-Time Pad'
                    />
                </Segment>
                <Segment>
                    <h3>Plaintext</h3>
                    <TextArea
                        name='plaintext'
                        className='otp'
                        value={this.state.plaintext}
                        onChange={this.handleInputChange}
                        placeholder='The message you want to send'
                    />
                </Segment>
                <Segment>
                    <h3>Ciphertext</h3>
                    <pre>{this.state.ciphertext || 'Enter your message above'}</pre>
                </Segment>
            </SegmentGroup>
            <br/>
            <Button onClick={this.handleSubmit}>Encrypt</Button>
        </>
    }
}

class Decrypt extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            otp: '', plaintext: '', ciphertext: '',
        }
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        try {
            let {otp, plaintext, ciphertext} = await decryptOTP(this.state.otp, this.state.ciphertext);
            this.setState({otp, plaintext, ciphertext});
        } catch (e) {
            console.error(e);
        }
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value});
    }

    render() {
        return <>
            <Header as='h2'>Decrypt</Header>
            <SegmentGroup>
                <Segment>
                    <h3>Key</h3>
                    <TextArea
                        name='otp'
                        className='otp'
                        value={this.state.otp}
                        onChange={this.handleInputChange}
                        placeholder='The random letters from your One-Time Pad'
                    />
                </Segment>
                <Segment>
                    <h3>Ciphertext</h3>
                    <TextArea
                        name='ciphertext'
                        className='otp'
                        value={this.state.ciphertext}
                        onChange={this.handleInputChange}
                        placeholder='The message you received'
                    />
                </Segment>
                <Segment>
                    <h3>Plaintext</h3>
                    <pre>{this.state.plaintext || 'Enter the encrypted message above'}</pre>
                </Segment>
            </SegmentGroup>
            <br/>
            <Button onClick={this.handleSubmit}>Decrypt</Button>
        </>
    }
}

function OTP() {
    useTitle('One Time Pad');

    const {t} = useContext(ThemeContext);

    let newPadURL = `http://${window.location.host}/api/otp/html`;
    let cheatSheetURL = `${process.env.PUBLIC_URL}/one-time-pad-cheat-sheet.pdf`;

    return <>
        <Header as='h1'>One-Time Pad</Header>
        <Header as='h4'>One-Time Pads can be used to encrypt your communications. This can be done by hand
            (yes, really) or in this app.</Header>
        <p {...t}>These messages are never stored and cannot be retrieved.</p>
        <Button primary href={newPadURL}>Generate New Pad</Button>
        <Button secondary href={cheatSheetURL}>Cheat Sheet PDF</Button>

        <Divider/>
        <Encrypt/>

        <Divider/>
        <Decrypt/>
    </>
}

function StatisticsPage() {
    useTitle('Statistics');

    const {s} = useContext(ThemeContext);

    const {statistics} = useStatistics();

    if (statistics === undefined) {
        return <>
            <Header as='h1'>Statistics</Header>
            <Segment><p {...s}>Failed to fetch statistics</p></Segment>
        </>;
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
        } = file_statistics;
        const {db_size} = global_statistics;
        return <>
            <Header as='h1'>Statistics</Header>
            <Header as='h2'>Files</Header>
            <Segment>
                <StatisticGroup>
                    <Statistic>
                        <StatisticValue>{toLocaleString(total_count)}</StatisticValue>
                        <StatisticLabel>All Files</StatisticLabel>
                    </Statistic>
                    <Statistic>
                        <StatisticValue>{humanFileSize(total_size)}</StatisticValue>
                        <StatisticLabel>Total Size</StatisticLabel>
                    </Statistic>
                </StatisticGroup>
            </Segment>
            <Segment>
                <StatisticGroup size='small'>
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
                </StatisticGroup>
            </Segment>
            <Segment>
                <StatisticGroup size='tiny'>
                    <Statistic>
                        <StatisticValue>{toLocaleString(zip_count)}</StatisticValue>
                        <StatisticLabel>ZIP</StatisticLabel>
                    </Statistic>
                    <Statistic color={mimetypeColor('audio/')}>
                        <StatisticValue>{toLocaleString(audio_count)}</StatisticValue>
                        <StatisticLabel>Audio</StatisticLabel>
                    </Statistic>
                </StatisticGroup>
            </Segment>

            <Header as='h2'>Database</Header>
            <Segment>
                <StatisticGroup>
                    <Statistic>
                        <StatisticValue>{humanFileSize(db_size)}</StatisticValue>
                        <StatisticLabel>Size</StatisticLabel>
                    </Statistic>
                </StatisticGroup>
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
            <Route path='otp' exact element={<OTP/>}/>
            <Route path='statistics' exact element={<StatisticsPage/>}/>
        </Routes>
    </PageContainer>
}
