import React from 'react';
import {Button, Divider, Segment, TextArea} from "semantic-ui-react";
import Container from "semantic-ui-react/dist/commonjs/elements/Container";
import {Route} from "react-router-dom";
import "../static/wrolpi.css";
import {decryptOTP, encryptOTP} from "../api";
import {PageContainer} from "./Common";

class Encrypt extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            otp: '',
            plaintext: '',
            ciphertext: '',
        }
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let {otp, plaintext, ciphertext} = await encryptOTP(this.state.otp, this.state.plaintext);
        this.setState({otp, plaintext, ciphertext});
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value});
    }

    render() {
        return (
            <>
                <h2>Encrypt</h2>
                <Segment.Group>
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
                </Segment.Group>
                <br/>
                <Button onClick={this.handleSubmit}>Encrypt</Button>
            </>
        )
    }
}

class Decrypt extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            otp: '',
            plaintext: '',
            ciphertext: '',
        }
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        let {otp, plaintext, ciphertext} = await decryptOTP(this.state.otp, this.state.ciphertext);
        this.setState({otp, plaintext, ciphertext});
    }

    handleInputChange = async (event, {name, value}) => {
        this.setState({[name]: value});
    }

    render() {
        return (
            <>
                <h2>Decrypt</h2>
                <Segment.Group>
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
                </Segment.Group>
                <br/>
                <Button onClick={this.handleSubmit}>Decrypt</Button>
            </>
        )
    }
}

class OTP extends React.Component {
    render() {
        let newPadURL = `http://${window.location.host}/api/otp/pdf`;
        let cheatSheetURL = `${process.env.PUBLIC_URL}/one-time-pad-cheat-sheet.pdf`;

        return (
            <div>
                <h1>One-Time Pad</h1>
                <h4>One-Time Pads can be used to encrypt your communications. This can be done by hand (yes, really) or
                    in this app.</h4>
                <p>These messages are never stored and cannot be retrieved.</p>
                <Button primary href={newPadURL}>Generate New Pad</Button>
                <Button secondary href={cheatSheetURL}>Cheat Sheet PDF</Button>

                <Divider/>
                <Encrypt/>

                <Divider/>
                <Decrypt/>
            </div>
        )
    }
}

export function AppsRoute(props) {
    return (
        <PageContainer>
            <Route path='/apps/otp' exact component={OTP}/>
        </PageContainer>
    )
}
