import React, {useContext, useState} from 'react';
import {Checkbox, Divider, Icon, Input, Radio, SegmentGroup} from "semantic-ui-react";
import {
    appendChecksum,
    decryptOTP,
    encryptOTP,
    formatMessage,
    generateHtml,
    OTP_CHARS,
    OTP_CHARS_ALPHA,
    stripChecksum,
    validateCharset
} from "../otp";
import {ErrorMessage, SimpleAccordion} from "../Common";
import {ThemeContext} from "../../contexts/contexts";
import {Button, Form, Header, Segment, TextArea} from "../Theme";

function Encrypt({chars, checksum}) {
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
    if (otp && plaintext && chars) {
        try {
            const raw = encryptOTP(otp, plaintext, chars).ciphertext;
            // When enabled, append a checksum character then re-group the whole message+checksum.
            ciphertext = checksum ? formatMessage(appendChecksum(raw, chars)) : raw;
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
                    : <pre>{ciphertext || (chars ? 'Enter your message above' : 'Set valid characters in Advanced options')}</pre>}
            </Segment>
        </SegmentGroup>
    </>
}

function Decrypt({chars, checksum}) {
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
    let checksumValid = null; // null = not applicable (checksum off or nothing to check)
    if (otp && ciphertext && chars) {
        try {
            let input = ciphertext;
            if (checksum) {
                // Only remove the trailing character when it actually verifies as a checksum, so a message without
                // one is never silently truncated.
                const {body, valid} = stripChecksum(ciphertext, chars);
                checksumValid = valid;
                input = body;
            }
            plaintext = decryptOTP(otp, input, chars).plaintext;
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
                {checksumValid !== null && <p>
                    <Icon name={checksumValid ? 'check' : 'times'} color={checksumValid ? 'green' : 'red'}/>
                    {checksumValid ? 'Checksum is valid' : 'Checksum is invalid'}
                </p>}
                {error
                    ? <ErrorMessage>{error}</ErrorMessage>
                    : <pre>{plaintext || (chars ? 'Enter the encrypted message above' : 'Set valid characters in Advanced options')}</pre>}
            </Segment>
        </SegmentGroup>
    </>
}

export function OneTimePadCalculator() {
    const {t} = useContext(ThemeContext);

    // The character set is a property of the pad: encrypt, decrypt, and generation all use the same alphabet.
    const [charsetKind, setCharsetKind] = useState('alphanumeric'); // 'alpha' | 'alphanumeric' | 'custom'
    const [customChars, setCustomChars] = useState('');
    const charsetError = charsetKind === 'custom' ? validateCharset(customChars) : null;
    const chars = charsetKind === 'alpha' ? OTP_CHARS_ALPHA
        : charsetKind === 'custom' ? customChars
            : OTP_CHARS;
    // A null charset means the custom set is not yet usable; encrypt/decrypt/generate are gated on this.
    const activeChars = charsetError ? null : chars;

    // Optional error-detection checksum appended to the ciphertext.
    const [checksum, setChecksum] = useState(false);

    let cheatSheetURL = `${process.env.PUBLIC_URL}/one-time-pad-cheat-sheet.pdf`;

    // Generate a new One-Time Pad entirely in the browser and open it in a new tab so it can be printed.  The pad is
    // never sent to or stored on the server.
    const handleGenerateNewPad = () => {
        const blob = new Blob([generateHtml(activeChars)], {type: 'text/html'});
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        // Release the blob handle once the new tab has had time to load it.
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    };

    return <>
        <Header as='h1'>One-Time Pad</Header>
        <Header as='h4'>One-Time Pads can be used to encrypt your communications. This can be done by hand
            (yes, really) or in this app.</Header>
        <p {...t}>These messages are never stored and cannot be retrieved.</p>
        <Button color='violet' disabled={!activeChars} onClick={handleGenerateNewPad}>Generate New Pad</Button>
        <Button secondary href={cheatSheetURL}>Cheat Sheet PDF</Button>

        <SimpleAccordion title='Advanced'>
            <Header as='h4'>Pad characters</Header>
            <Form>
                <Form.Field>
                    <Radio label='A–Z' name='charset' value='alpha'
                           checked={charsetKind === 'alpha'} onChange={() => setCharsetKind('alpha')}/>
                </Form.Field>
                <Form.Field>
                    <Radio label='A–Z and 0–9' name='charset' value='alphanumeric'
                           checked={charsetKind === 'alphanumeric'} onChange={() => setCharsetKind('alphanumeric')}/>
                </Form.Field>
                <Form.Field>
                    <Radio label='Custom' name='charset' value='custom'
                           checked={charsetKind === 'custom'} onChange={() => setCharsetKind('custom')}/>
                </Form.Field>
            </Form>
            {charsetKind === 'custom' && <>
                <Input
                    fluid
                    value={customChars}
                    placeholder='e.g. ABCDEF0123'
                    onChange={(e, {value}) => setCustomChars(value)}
                />
                {charsetError && <ErrorMessage>{charsetError}</ErrorMessage>}
            </>}

            <Header as='h4'>Error detection</Header>
            <Checkbox
                label='Append error-detection checksum'
                checked={checksum}
                onChange={() => setChecksum(!checksum)}
            />
        </SimpleAccordion>

        <Divider/>
        <Encrypt chars={activeChars} checksum={checksum}/>

        <Divider/>
        <Decrypt chars={activeChars} checksum={checksum}/>
    </>
}
