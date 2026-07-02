import React from "react";
import {fireEvent, screen} from "@testing-library/react";
import {renderWithProviders} from "../../test-utils";
import {OneTimePadCalculator} from "./OneTimePadCalculator";

describe('OneTimePadCalculator', () => {
    test('renders the pad tools', () => {
        renderWithProviders(<OneTimePadCalculator/>);
        expect(screen.getByText('One-Time Pad')).toBeTruthy();
        expect(screen.getByText('Generate New Pad')).toBeTruthy();
        expect(screen.getByText('Encrypt')).toBeTruthy();
        expect(screen.getByText('Decrypt')).toBeTruthy();
    });

    test('encrypts live using the entered key', () => {
        const {container} = renderWithProviders(<OneTimePadCalculator/>);
        // The Encrypt section's Key and Plaintext textareas are the first two on the page.
        const keys = container.querySelectorAll('textarea[name="otp"]');
        const plaintext = container.querySelector('textarea[name="plaintext"]');
        fireEvent.change(keys[0], {target: {value: 'ABCDE'}});
        fireEvent.change(plaintext, {target: {value: 'HELLO'}});
        // Ciphertext is rendered into a <pre> and differs from the plaintext once a key is present.
        const pres = container.querySelectorAll('pre');
        const ciphertext = pres[0].textContent;
        expect(ciphertext).toBeTruthy();
        expect(ciphertext).not.toEqual('HELLO');
    });
});
