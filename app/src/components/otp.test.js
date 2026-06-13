import {webcrypto} from 'crypto';
import {decryptOTP, encryptOTP, formatMessage, generateHtml} from './otp';

// jsdom does not always provide window.crypto; real browsers always do.  Polyfill it for the generation tests.
if (!window.crypto || !window.crypto.getRandomValues) {
    window.crypto = webcrypto;
}

// These cases are migrated from the original backend tests (modules/otp/test/test_otp.py and test_api.py); the
// expected data is identical so the browser implementation matches the old server behavior exactly.

describe('encryptOTP', () => {
    test.each([
        ['', '', ''],
        ['A', 'A', 'A'],
        ['B', 'B', 'C'],
        ['9', '9', '8'],
        ['W', 'H', '3'],
        ['W8JD7', 'HELLO', '3CUOL'],
        ['XMCKL', 'HELLO', '4QNVZ'],
        [
            // This message says: TEST THE ENCRYPTION OF A LONG MESSAGE THE SPACES SHOULDNT MATTER
            // The message is shorter than the OTP, this is fine.  The ciphertext should be the same
            // length as the message.
            'V4YPT RCJLZ QZVSD 0U2E6 OOKNU\nZDH8F 4XQ76 OR6EK J0TRG 0G0HU\nS4BUJ',
            'TESTT HEENC RYPTI ONOFA LONGM\nESSAG ETHES PACES SHOUL DNTMA\nTTER',
            'E8G8C YGNY1 7NABL E7GJ6 Z2XT6\n3VZ8L 8GXBO 3R8I2 177BR 3TJTU\nBNFB',
        ],
        // From the original API test (test_api.py).
        ['asdf', 'asdf', 'AAGK'],
    ])('encrypts otp=%j plaintext=%j', (otp, plaintext, ciphertext) => {
        const result = encryptOTP(otp, plaintext);
        expect(result).toEqual({
            otp: formatMessage(otp.toUpperCase().replace(/\s/g, '')),
            plaintext: formatMessage(plaintext.toUpperCase().replace(/\s/g, '')),
            ciphertext,
        });

        // Whitespace is ignored.
        const paddedPlaintext = `\t   ${plaintext}`;
        const paddedOtp = `\n ${otp} `;
        const paddedResult = encryptOTP(paddedOtp, paddedPlaintext);
        expect(paddedResult).toEqual({
            otp: formatMessage(otp.toUpperCase().replace(/\s/g, '')),
            plaintext: formatMessage(plaintext.toUpperCase().replace(/\s/g, '')),
            ciphertext,
        });
    });
});

describe('decryptOTP', () => {
    test.each([
        ['', '', ''],
        ['A', 'A', 'A'],
        ['B', 'C', 'B'],
        ['W', '3', 'H'],
        ['9', '8', '9'],
        ['W8JD7', '3CUOL', 'HELLO'],
        ['XMCKL', '4QNVZ', 'HELLO'],
        [
            'V4YPT RCJLZ QZVSD 0U2E6 OOKNU\nZDH8F 4XQ76 OR6EK J0TRG 0G0HU\nS4BUJ',
            'E8G8C YGNY1 7NABL E7GJ6 Z2XT6\n3VZ8L 8GXBO 3R8I2 177BR 3TJTU\nBNFB',
            'TESTT HEENC RYPTI ONOFA LONGM\nESSAG ETHES PACES SHOUL DNTMA\nTTER',
        ],
        // From the original API test (test_api.py).
        ['asdf', 'aagk', 'ASDF'],
    ])('decrypts otp=%j ciphertext=%j', (otp, ciphertext, plaintext) => {
        const result = decryptOTP(otp, ciphertext);
        expect(result).toEqual({
            otp: formatMessage(otp.toUpperCase().replace(/\s/g, '')),
            ciphertext: formatMessage(ciphertext.toUpperCase().replace(/\s/g, '')),
            plaintext,
        });
    });
});

describe('formatMessage', () => {
    test.each([
        ['ABC', 'ABC'],
        ['ABCDEFG', 'ABCDE FG'],
        ['SOMEMESSAGE', 'SOMEM ESSAG E'],
        [
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890',
            'ABCDE FGHIJ KLMNO PQRST UVWXY\nZ0123 45678 90',
        ],
        [
            'A'.repeat(94),
            'AAAAA AAAAA AAAAA AAAAA AAAAA\n' +
            'AAAAA AAAAA AAAAA AAAAA AAAAA\n' +
            'AAAAA AAAAA AAAAA AAAAA AAAAA\n' +
            'AAAAA AAAAA AAAAA AAAA',
        ],
    ])('formats %j', (message, expected) => {
        expect(formatMessage(message)).toEqual(expected);
    });
});

describe('generateHtml', () => {
    test('generates a OTP HTML page', () => {
        expect(generateHtml()).toBeTruthy();
    });
});
