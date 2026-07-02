import React from "react";
import {screen} from "@testing-library/react";
import {renderWithProviders} from "../../test-utils";
import {VinDecoderCalculator} from "./VinDecoderCalculator";

describe('VinDecoderCalculator', () => {
    test('renders the decoder and prompts for input', () => {
        // An empty VIN never triggers an API call (useVINDecoder returns early), so this
        // renders without any fetch mocking.
        renderWithProviders(<VinDecoderCalculator/>);
        expect(screen.getByText('VIN Number Decoder')).toBeTruthy();
        expect(screen.getByText('Enter a VIN number above')).toBeTruthy();
    });
});
