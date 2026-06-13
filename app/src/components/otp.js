// One-Time Pad encryption/decryption.  This is performed entirely in the browser; messages are never sent to the
// server.  This is a JavaScript port of the original Python implementation (modules/otp/lib.py).

// These are the only characters we support.
export const OTP_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
// The number of characters in each group, separated by spaces.
export const GROUP_SIZE = 5;
// The groups in each row of a message, separated by newlines.  This is small to allow for mobile phones.
export const GROUP_COUNT = 5;

const CHARS_LEN = OTP_CHARS.length;
const WHITESPACE = /\s/g;

export class InvalidOTP extends Error {
    constructor(message = 'OTP has invalid characters') {
        super(message);
        this.name = 'InvalidOTP';
    }
}

export class InvalidPlaintext extends Error {
    constructor(message = 'Plaintext has invalid characters') {
        super(message);
        this.name = 'InvalidPlaintext';
    }
}

export class InvalidCiphertext extends Error {
    constructor(message = 'Ciphertext has invalid characters') {
        super(message);
        this.name = 'InvalidCiphertext';
    }
}

// Split an iterable into chunks of the defined size.
function chunks(it, size) {
    const result = [];
    for (let i = 0; i < it.length; i += size) {
        result.push(it.slice(i, i + size));
    }
    return result;
}

// Formats messages in the style of a One-Time-Pad.  Usually 5 characters per group.
//
//   formatMessage('SOMEMESSAGE') === 'SOMEM ESSAG E'
export function formatMessage(message, groupCount = GROUP_COUNT) {
    const groups = chunks(message, GROUP_SIZE);
    const rows = chunks(groups, groupCount);
    return rows.map(row => row.join(' ')).join('\n');
}

function validateMessage(message, ErrorClass) {
    message = message.toUpperCase();
    message = message.replace(WHITESPACE, '');

    for (const char of message) {
        if (!OTP_CHARS.includes(char)) {
            throw new ErrorClass();
        }
    }

    return message;
}

function encryptChar(plaintext, otp) {
    const calculated = (OTP_CHARS.indexOf(plaintext) + OTP_CHARS.indexOf(otp)) % CHARS_LEN;
    return OTP_CHARS[calculated];
}

function decryptChar(ciphertext, otp) {
    // JavaScript's % can return negative values; add CHARS_LEN before the modulo to keep it positive.
    const calculated = (OTP_CHARS.indexOf(ciphertext) - OTP_CHARS.indexOf(otp) + CHARS_LEN) % CHARS_LEN;
    return OTP_CHARS[calculated];
}

// Encrypt a plaintext message using an OTP.
export function encryptOTP(otp, plaintext) {
    otp = validateMessage(otp, InvalidOTP);
    plaintext = validateMessage(plaintext, InvalidPlaintext);

    if (plaintext.length > otp.length) {
        throw new InvalidPlaintext('Plaintext is longer than OTP');
    }

    let ciphertext = '';
    for (let i = 0; i < plaintext.length; i++) {
        ciphertext += encryptChar(plaintext[i], otp[i]);
    }

    return {
        ciphertext: formatMessage(ciphertext),
        otp: formatMessage(otp),
        plaintext: formatMessage(plaintext),
    };
}

// Decrypt an encrypted message that was encrypted with an OTP.
export function decryptOTP(otp, ciphertext) {
    otp = validateMessage(otp, InvalidOTP);
    ciphertext = validateMessage(ciphertext, InvalidCiphertext);

    if (ciphertext.length > otp.length) {
        throw new InvalidCiphertext('Ciphertext is longer than OTP');
    }

    let plaintext = '';
    for (let i = 0; i < ciphertext.length; i++) {
        plaintext += decryptChar(ciphertext[i], otp[i]);
    }

    return {
        plaintext: formatMessage(plaintext),
        ciphertext: formatMessage(ciphertext),
        otp: formatMessage(otp),
    };
}

function getCrypto() {
    const cryptoObj = typeof window !== 'undefined' && window.crypto;
    if (!cryptoObj || !cryptoObj.getRandomValues) {
        throw new Error('A cryptographically secure random number generator is not available.');
    }
    return cryptoObj;
}

// Choose a single OTP character using a cryptographically secure RNG.  Rejection sampling is used to avoid modulo bias.
function generateChar() {
    const cryptoObj = getCrypto();
    const max = 256 - (256 % CHARS_LEN);
    const buffer = new Uint8Array(1);
    let value;
    do {
        cryptoObj.getRandomValues(buffer);
        value = buffer[0];
    } while (value >= max);
    return OTP_CHARS[value % CHARS_LEN];
}

// Create an OTP message.  Format it for ease of use.
export function generateMessage() {
    let message = '';
    // Use 16 groups per line because this page will be printed.
    for (let i = 0; i < 320; i++) {
        message += generateChar();
    }
    return formatMessage(message, 16);
}

const PAGE_HTML = `
<html>
<title>One Time Pad - Unique, just for you</title>
<style>
/* Remove decoration from links so they are readable when printed */
a { text-decoration: none; }
</style>
<body>
{messages}


Print this page and distribute the copies (along with the <a href="https://lrnsr.co/aY6m">One Time Pad Cheat Sheet
https://lrnsr.co/aY6m</a>) to all members of your group that you trust to receive your encrypted messages.  Every
person must have their OWN copy of this "One Time Pad" to encrypt and decrypt messages.
<br>
<b>Use each message ONLY ONCE.</b>  Cut off and burn each message from this paper as it is used.
<br>
To learn how to use this page, please visit: <a href="https://lrnsr.co/H7Za">https://lrnsr.co/H7Za</a>
</body>
</html>
`;

// Create an HTML One-Time Pad page.  This page will have instructions on how to use the OTP.
export function generateHtml() {
    const messages = [];
    for (let i = 1; i <= 8; i++) {
        messages.push(`<pre>MESSAGE ${i}</pre><pre>${generateMessage()}</pre>`);
    }
    return PAGE_HTML.replace('{messages}', messages.join('\n\n'));
}
