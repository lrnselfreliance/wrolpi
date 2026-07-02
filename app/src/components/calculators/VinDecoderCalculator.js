import React, {useContext} from 'react';
import {Input, TableCell, TableRow} from "semantic-ui-react";
import {ThemeContext} from "../../contexts/contexts";
import {useVINDecoder} from "../../hooks/customHooks";
import {Header, Table} from "../Theme";

export function VinDecoderCalculator() {
    const {t} = useContext(ThemeContext);

    const basicKeys = ['Country', 'Manufacturer', 'Region', 'Years'];
    const detailsKeys = ['Body', 'Engine', 'Model', 'Plant', 'Transmission', 'Serial'];

    const {value, setValue, vin} = useVINDecoder();

    let body = <p {...t}>Enter a VIN number above</p>;
    if (value && !vin) {
        body = <p {...t}>VIN number is invalid</p>;
    }
    if (vin && vin['country']) {
        let details = <p {...t}>No details</p>;
        if (vin['body']) {
            details = <Table celled columns={2} {...t}>
                {detailsKeys.map(i => <TableRow key={i}>
                    <TableCell width={5}><b>{i}</b></TableCell>
                    <TableCell width={11}>{vin[i.toLowerCase()] || '(Unknown)'}</TableCell>
                </TableRow>)}
            </Table>;
        }
        body = <>
            <Table celled columns={2} {...t}>
                {basicKeys.map(i => <TableRow key={i}>
                    <TableCell width={5}><b>{i}</b></TableCell>
                    <TableCell width={11}>{vin[i.toLowerCase()]}</TableCell>
                </TableRow>)}
            </Table>
            <Header as='h3'>Details</Header>
            {details}
        </>;
    }

    return <>
        <Header as='h1'>VIN Number Decoder</Header>
        <Input
            size='large'
            label='VIN'
            value={value}
            onChange={e => setValue(e.target.value)}
        />

        <Header as='h2'>Decoded</Header>
        {body}
    </>
}
