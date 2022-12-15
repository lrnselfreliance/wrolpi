import React, {useContext} from 'react';
import {Divider, SegmentGroup, StatisticLabel, StatisticValue} from "semantic-ui-react";
import {Route, Routes} from "react-router-dom";
import "../static/wrolpi.css";
import {decryptOTP, encryptOTP} from "../api";
import {PageContainer, useTitle} from "./Common";
import {ThemeContext} from "../contexts/contexts";
import {Button, Header, Loader, Segment, Statistic, StatisticGroup, TextArea} from "./Theme";
import {useFileStatistics} from "../hooks/customHooks";

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

function FileStatistics() {
    useTitle('File Statistics');

    const {s} = useContext(ThemeContext);

    const {statistics} = useFileStatistics();

    let body = <Loader inline active/>;

    if (statistics === undefined) {
        body = <p {...s}>Failed to fetch statistics</p>;
    }

    if (statistics !== undefined && statistics !== null) {
        const {total_count, video_count, pdf_count, ebook_count, archive_count, image_count, zip_count} = statistics;
        body = <>
            <StatisticGroup>
                <Statistic>
                    <StatisticValue>{total_count}</StatisticValue>
                    <StatisticLabel>All Files</StatisticLabel>
                </Statistic>
            </StatisticGroup>
            <StatisticGroup size='small'>
                <Statistic color='blue'>
                    <StatisticValue>{video_count}</StatisticValue>
                    <StatisticLabel>Videos</StatisticLabel>
                </Statistic>
                <Statistic color='red'>
                    <StatisticValue>{pdf_count}</StatisticValue>
                    <StatisticLabel>PDFs</StatisticLabel>
                </Statistic>
                <Statistic color='yellow'>
                    <StatisticValue>{ebook_count}</StatisticValue>
                    <StatisticLabel>eBooks</StatisticLabel>
                </Statistic>
                <Statistic color='green'>
                    <StatisticValue>{archive_count}</StatisticValue>
                    <StatisticLabel>Archives</StatisticLabel>
                </Statistic>
                <Statistic color='pink'>
                    <StatisticValue>{image_count}</StatisticValue>
                    <StatisticLabel>Images</StatisticLabel>
                </Statistic>
            </StatisticGroup>
            <StatisticGroup>
                <Statistic color='grey'>
                    <StatisticValue>{zip_count}</StatisticValue>
                    <StatisticLabel>ZIP</StatisticLabel>
                </Statistic>
            </StatisticGroup>
        </>;
    }

    return <>
        <Header as='h1'>File Statistics</Header>
        <Segment>
            {body}
        </Segment>
    </>
}

export function AppsRoute(props) {
    return (<PageContainer>
        <Routes>
            <Route path='otp' exact element={<OTP/>}/>
            <Route path='file_statistics' exact element={<FileStatistics/>}/>
        </Routes>
    </PageContainer>)
}
