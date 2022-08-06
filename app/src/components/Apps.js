import React, {useContext} from 'react';
import {Divider, SegmentGroup} from "semantic-ui-react";
import {Route, Routes} from "react-router-dom";
import "../static/wrolpi.css";
import {decryptOTP, encryptOTP} from "../api";
import {PageContainer} from "./Common";
import {ThemeContext} from "../contexts/contexts";
import {Button, Header, Segment, TextArea} from "./Theme";

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

export function AppsRoute(props) {
    return (<PageContainer>
        <Routes>
            <Route path='otp' exact element={<OTP/>}/>
        </Routes>
    </PageContainer>)
}
