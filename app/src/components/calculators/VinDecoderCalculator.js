import React from 'react';
import {useVINDecoder} from "../../hooks/customHooks";
import {Header, Table, TextInput} from "../ui";

export function VinDecoderCalculator() {
    const basicKeys = ['Country', 'Manufacturer', 'Region', 'Years'];
    const detailsKeys = ['Body', 'Engine', 'Model', 'Plant', 'Transmission', 'Serial'];

    const {value, setValue, vin} = useVINDecoder();

    let body = <p>Enter a VIN number above</p>;
    if (value && !vin) {
        body = <p>VIN number is invalid</p>;
    }
    if (vin && vin['country']) {
        let details = <p>No details</p>;
        if (vin['body']) {
            details = <Table>
                <Table.Body>
                    {detailsKeys.map(i => <Table.Row key={i}>
                        <Table.Cell width={5}><b>{i}</b></Table.Cell>
                        <Table.Cell width={11}>{vin[i.toLowerCase()] || '(Unknown)'}</Table.Cell>
                    </Table.Row>)}
                </Table.Body>
            </Table>;
        }
        body = <>
            <Table>
                <Table.Body>
                    {basicKeys.map(i => <Table.Row key={i}>
                        <Table.Cell width={5}><b>{i}</b></Table.Cell>
                        <Table.Cell width={11}>{vin[i.toLowerCase()]}</Table.Cell>
                    </Table.Row>)}
                </Table.Body>
            </Table>
            <Header as='h3'>Details</Header>
            {details}
        </>;
    }

    return <>
        <Header as='h1'>VIN Number Decoder</Header>
        <TextInput
            size='lg'
            label='VIN'
            value={value}
            onChange={e => setValue(e.target.value)}
        />

        <Header as='h2'>Decoded</Header>
        {body}
    </>
}
