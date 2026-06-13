// One-Time Pad encryption/decryption.  This is performed entirely in the browser; messages are never sent to the
// server.  This is a JavaScript port of the original Python implementation (modules/otp/lib.py).

// The default character set: letters and digits.
export const OTP_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
// A letters-only character set, easiest to work by hand.
export const OTP_CHARS_ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
// The number of characters in each group, separated by spaces.
export const GROUP_SIZE = 5;
// The groups in each row of a message, separated by newlines.  This is small to allow for mobile phones.
export const GROUP_COUNT = 5;

const WHITESPACE = /\s/g;

// A character set whose characters are all uppercase can have its input auto-uppercased for convenience.  A custom
// set containing lowercase is treated case-sensitively (the input is used verbatim).
const shouldUppercase = (chars) => chars === chars.toUpperCase();

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

export class InvalidMessage extends Error {
    constructor(message = 'Message has invalid characters') {
        super(message);
        this.name = 'InvalidMessage';
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

function validateMessage(message, ErrorClass, chars) {
    if (shouldUppercase(chars)) {
        message = message.toUpperCase();
    }
    message = message.replace(WHITESPACE, '');

    for (const char of message) {
        if (!chars.includes(char)) {
            throw new ErrorClass();
        }
    }

    return message;
}

function encryptChar(plaintext, otp, chars) {
    const calculated = (chars.indexOf(plaintext) + chars.indexOf(otp)) % chars.length;
    return chars[calculated];
}

function decryptChar(ciphertext, otp, chars) {
    // JavaScript's % can return negative values; add chars.length before the modulo to keep it positive.
    const calculated = (chars.indexOf(ciphertext) - chars.indexOf(otp) + chars.length) % chars.length;
    return chars[calculated];
}

// Validate a character set.  Returns an error message string, or null when the set is usable.
export function validateCharset(chars) {
    if (!chars || chars.length < 2) {
        return 'Enter at least 2 characters';
    }
    if (chars.length > 256) {
        return 'Too many characters (max 256)';
    }
    if (/\s/.test(chars)) {
        return 'Characters cannot contain spaces';
    }
    if (new Set(chars).size !== chars.length) {
        return 'Characters must be unique';
    }
    return null;
}

// Encrypt a plaintext message using an OTP and the given character set.
export function encryptOTP(otp, plaintext, chars = OTP_CHARS) {
    otp = validateMessage(otp, InvalidOTP, chars);
    plaintext = validateMessage(plaintext, InvalidPlaintext, chars);

    if (plaintext.length > otp.length) {
        throw new InvalidPlaintext('Plaintext is longer than OTP');
    }

    let ciphertext = '';
    for (let i = 0; i < plaintext.length; i++) {
        ciphertext += encryptChar(plaintext[i], otp[i], chars);
    }

    return {
        ciphertext: formatMessage(ciphertext),
        otp: formatMessage(otp),
        plaintext: formatMessage(plaintext),
    };
}

// Decrypt an encrypted message that was encrypted with an OTP and the given character set.
export function decryptOTP(otp, ciphertext, chars = OTP_CHARS) {
    otp = validateMessage(otp, InvalidOTP, chars);
    ciphertext = validateMessage(ciphertext, InvalidCiphertext, chars);

    if (ciphertext.length > otp.length) {
        throw new InvalidCiphertext('Ciphertext is longer than OTP');
    }

    let plaintext = '';
    for (let i = 0; i < ciphertext.length; i++) {
        plaintext += decryptChar(ciphertext[i], otp[i], chars);
    }

    return {
        plaintext: formatMessage(plaintext),
        ciphertext: formatMessage(ciphertext),
        otp: formatMessage(otp),
    };
}

// Calculate a position-weighted checksum character for a message: sum(position * value) mod N, where position is
// 1-indexed and value is the character's index in the set.  Position weighting catches transposition errors.
export function calculateChecksum(message, chars = OTP_CHARS) {
    message = validateMessage(message, InvalidMessage, chars);
    let total = 0;
    for (let i = 0; i < message.length; i++) {
        total += (i + 1) * chars.indexOf(message[i]);
    }
    return chars[total % chars.length];
}

// Append a checksum character to a message.
export function appendChecksum(message, chars = OTP_CHARS) {
    message = validateMessage(message, InvalidMessage, chars);
    return message + calculateChecksum(message, chars);
}

// Verify a message whose last character is a checksum.  Returns true when the checksum matches.
export function verifyChecksum(messageWithChecksum, chars = OTP_CHARS) {
    messageWithChecksum = validateMessage(messageWithChecksum, InvalidMessage, chars);
    if (messageWithChecksum.length < 2) {
        return false;
    }
    return calculateChecksum(messageWithChecksum.slice(0, -1), chars) === messageWithChecksum.slice(-1);
}

// Interpret a received message that may carry a trailing checksum character.  The last character is removed ONLY when
// it verifies as the checksum of the preceding characters; otherwise the message is returned unchanged.  This avoids
// silently truncating a legitimate character from a message that does not actually carry a checksum.
// Returns {body, valid}: `body` is the message to decrypt, `valid` is whether a checksum was present and matched.
export function stripChecksum(received, chars = OTP_CHARS) {
    const cleaned = validateMessage(received, InvalidMessage, chars);
    if (cleaned.length >= 2 && calculateChecksum(cleaned.slice(0, -1), chars) === cleaned.slice(-1)) {
        return {body: cleaned.slice(0, -1), valid: true};
    }
    return {body: cleaned, valid: false};
}

function getCrypto() {
    const cryptoObj = typeof window !== 'undefined' && window.crypto;
    if (!cryptoObj || !cryptoObj.getRandomValues) {
        throw new Error('A cryptographically secure random number generator is not available.');
    }
    return cryptoObj;
}

// Choose a single OTP character using a cryptographically secure RNG.  Rejection sampling is used to avoid modulo bias.
function generateChar(chars) {
    const cryptoObj = getCrypto();
    const max = 256 - (256 % chars.length);
    const buffer = new Uint8Array(1);
    let value;
    do {
        cryptoObj.getRandomValues(buffer);
        value = buffer[0];
    } while (value >= max);
    return chars[value % chars.length];
}

// Create an OTP message.  Format it for ease of use.
export function generateMessage(chars = OTP_CHARS) {
    let message = '';
    // Use 16 groups per line because this page will be printed.
    for (let i = 0; i < 320; i++) {
        message += generateChar(chars);
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
<pre>Characters: {chars}</pre>

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
export function generateHtml(chars = OTP_CHARS) {
    const messages = [];
    for (let i = 1; i <= 8; i++) {
        messages.push(`<pre>MESSAGE ${i}</pre><pre>${generateMessage(chars)}</pre>`);
    }
    // Use function replacers so a '$' in a custom character set is not treated as a replacement pattern.
    return PAGE_HTML.replace('{messages}', () => messages.join('\n\n')).replace('{chars}', () => chars);
}
