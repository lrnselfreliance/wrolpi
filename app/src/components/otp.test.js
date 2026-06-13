import {webcrypto} from 'crypto';
import {
    appendChecksum,
    calculateChecksum,
    decryptOTP,
    encryptOTP,
    formatMessage,
    generateHtml,
    generateMessage,
    InvalidCiphertext,
    InvalidOTP,
    InvalidPlaintext,
    OTP_CHARS,
    OTP_CHARS_ALPHA,
    stripChecksum,
    validateCharset,
    verifyChecksum
} from './otp';

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

describe('custom character sets', () => {
    test('A–Z only encrypts with the classic Vigenère vector', () => {
        // With 0–9 absent (mod 26), HELLO + XMCKL = EQNVZ — different from the 36-char result.
        const result = encryptOTP('XMCKL', 'HELLO', OTP_CHARS_ALPHA);
        expect(result.ciphertext).toEqual('EQNVZ');
        expect(decryptOTP('XMCKL', 'EQNVZ', OTP_CHARS_ALPHA).plaintext).toEqual('HELLO');
    });

    test('a digit is rejected when the set is A–Z only', () => {
        expect(() => encryptOTP('ABCDE', 'HELL0', OTP_CHARS_ALPHA)).toThrow('Plaintext has invalid characters');
    });

    test('round-trips through a custom numeric set', () => {
        const chars = '0123456789';
        const {ciphertext} = encryptOTP('48271', '13579', chars);
        expect(decryptOTP('48271', ciphertext, chars).plaintext).toEqual('13579');
    });

    test('an out-of-set character throws', () => {
        expect(() => encryptOTP('01234', 'ABCDE', '0123456789')).toThrow('Plaintext has invalid characters');
    });

    test('an all-uppercase custom set auto-uppercases input', () => {
        // The set is all uppercase, so lowercase input is folded to uppercase (like the built-in sets).
        const chars = 'ABCDEF';
        expect(encryptOTP('aabbcc', 'abcdef', chars)).toEqual(encryptOTP('AABBCC', 'ABCDEF', chars));
    });

    test('a custom set with lowercase is case-sensitive', () => {
        // The set contains lowercase, so input is used verbatim; uppercase input is not in the set.
        expect(encryptOTP('abcde', 'abcde', 'abcde').ciphertext).toBeTruthy();
        expect(() => encryptOTP('abcde', 'ABCDE', 'abcde')).toThrow('Plaintext has invalid characters');
    });
});

describe('validateCharset', () => {
    test.each([
        ['ABCDEFGHIJKLMNOPQRSTUVWXYZ', null],
        ['0123456789', null],
        ['', 'Enter at least 2 characters'],
        ['A', 'Enter at least 2 characters'],
        ['AABC', 'Characters must be unique'],
        ['AB CD', 'Characters cannot contain spaces'],
        ['A'.repeat(257), 'Too many characters (max 256)'],
    ])('validates %j', (chars, expected) => {
        expect(validateCharset(chars)).toEqual(expected);
    });
});

describe('checksum', () => {
    // Vectors adapted from the original backend plan (otp-checksum.md), default 36-char set.
    test.each([
        ['', 'A'],
        ['A', 'A'],
        ['B', 'B'],
        ['HELLO', 'S'], // 7+8+33+44+70 = 162 mod 36 = 18 = 'S'
        ['HLELO', 'L'], // transposition produces a different checksum (162→155, 155 mod 36 = 11 = 'L')
    ])('calculateChecksum(%j) = %j', (message, expected) => {
        expect(calculateChecksum(message)).toEqual(expected);
    });

    test.each([
        ['HELLOS', true],
        ['HELLOX', false], // wrong checksum
        ['HLELOS', false], // transposed message, original checksum
    ])('verifyChecksum(%j) = %j', (messageWithChecksum, expected) => {
        expect(verifyChecksum(messageWithChecksum)).toEqual(expected);
    });

    test('appendChecksum adds the checksum character', () => {
        expect(appendChecksum('HELLO')).toEqual('HELLOS');
    });

    test('checksum follows the character set', () => {
        // With A–Z (mod 26): 162 mod 26 = 6 = 'G', not 'S'.
        expect(calculateChecksum('HELLO', OTP_CHARS_ALPHA)).toEqual('G');
    });

    test('checksum protects an encrypted message end-to-end', () => {
        const {ciphertext} = encryptOTP('W8JD7', 'HELLO'); // '3CUOL'
        expect(appendChecksum(ciphertext)).toEqual('3CUOLY');
        // A transposition in the ciphertext yields a different checksum.
        expect(calculateChecksum('3UCOL')).not.toEqual(calculateChecksum('3CUOL'));
    });
});

describe('validation errors', () => {
    test('an invalid OTP character throws InvalidOTP', () => {
        expect(() => encryptOTP('A!', 'AB')).toThrow(InvalidOTP);
        expect(() => decryptOTP('A!', 'AB')).toThrow(InvalidOTP);
    });

    test('an invalid plaintext character throws InvalidPlaintext', () => {
        expect(() => encryptOTP('ABC', 'A!')).toThrow(InvalidPlaintext);
    });

    test('an invalid ciphertext character throws InvalidCiphertext', () => {
        expect(() => decryptOTP('ABC', 'A!')).toThrow(InvalidCiphertext);
    });

    test('plaintext longer than the OTP throws', () => {
        expect(() => encryptOTP('AB', 'ABC')).toThrow('Plaintext is longer than OTP');
    });

    test('ciphertext longer than the OTP throws', () => {
        expect(() => decryptOTP('AB', 'ABC')).toThrow('Ciphertext is longer than OTP');
    });
});

describe('encrypt/decrypt roundtrip', () => {
    // A small deterministic PRNG keeps the fuzz reproducible (no reliance on Math.random/crypto).
    let seed = 123456789;
    const rand = () => {
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;
        return seed / 0x7fffffff;
    };
    const pick = (chars, n) => {
        let out = '';
        for (let i = 0; i < n; i++) out += chars[Math.floor(rand() * chars.length)];
        return out;
    };

    test.each([
        OTP_CHARS_ALPHA,
        OTP_CHARS,
        '0123456789',
        'abcdef0123', // mixed-case-safe custom set (lowercase => case-sensitive, no uppercasing)
    ])('recovers the plaintext over %j', (chars) => {
        for (let n = 0; n < 50; n++) {
            const len = 1 + Math.floor(rand() * 20);
            const plaintext = pick(chars, len);
            const otp = pick(chars, len + Math.floor(rand() * 10)); // OTP at least as long as the message
            const {ciphertext} = encryptOTP(otp, plaintext, chars);
            expect(decryptOTP(otp, ciphertext, chars).plaintext).toEqual(formatMessage(plaintext));
        }
    });
});

describe('stripChecksum', () => {
    test('removes a valid trailing checksum', () => {
        // calculateChecksum('HELLO') === 'S'
        expect(stripChecksum('HELLOS')).toEqual({body: 'HELLO', valid: true});
    });

    test('does NOT truncate a message that has no valid checksum', () => {
        // Regression: with the checksum option on, the UI used to blindly drop the last character.  'HELLO' has no
        // checksum (its checksum would be 'S'), so it must be returned intact rather than decoded as 'HELL'.
        expect(stripChecksum('HELLO')).toEqual({body: 'HELLO', valid: false});
    });

    test('leaves a corrupted checksummed message intact and flags it invalid', () => {
        expect(stripChecksum('HELLOX')).toEqual({body: 'HELLOX', valid: false});
    });

    test('mirrors the decrypt UI flow end-to-end', () => {
        const otp = 'W8JD7';
        const raw = encryptOTP(otp, 'HELLO').ciphertext; // '3CUOL'
        const transmitted = formatMessage(appendChecksum(raw)); // '3CUOL Y'
        const {body, valid} = stripChecksum(transmitted);
        expect(valid).toBe(true);
        expect(decryptOTP(otp, body).plaintext).toEqual('HELLO');
    });
});

describe('generateMessage', () => {
    test('produces 320 characters from the default set', () => {
        const message = generateMessage().replace(/\s/g, '');
        expect(message).toHaveLength(320);
        expect([...message].every(c => OTP_CHARS.includes(c))).toBe(true);
    });

    test('only uses the given character set', () => {
        const chars = 'AB';
        const message = generateMessage(chars).replace(/\s/g, '');
        expect(message).toHaveLength(320);
        expect([...message].every(c => chars.includes(c))).toBe(true);
    });
});

describe('generateHtml', () => {
    test('generates a OTP HTML page', () => {
        expect(generateHtml()).toBeTruthy();
    });

    test('labels the page with the character set it used', () => {
        expect(generateHtml(OTP_CHARS_ALPHA)).toContain('Characters: ABCDEFGHIJKLMNOPQRSTUVWXYZ');
    });
});
