import React from "react";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Header, Table} from "../Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {roundDigits} from "../Common";
import {ColoredInput} from "../Apps";

function convertFeetToFeetAndInches(decimalFeet) {
    // Extract the integer part for feet
    const feet = Math.floor(decimalFeet);
    // Calculate the remainder in feet and convert it to inches (1 foot = 12 inches)
    const inches = Math.round((decimalFeet - feet) * 12);

    return [feet, inches];
}

const defaultMhzInputValue = '144.2';

export function DipoleAntennaCalculator() {
    const [mhz, setMhz] = React.useState(144.2);
    const [wave, setWave] = React.useState(2.08);
    const [mhzInputValue, setMhzInputValue] = React.useState(defaultMhzInputValue);
    const [waveInputValue, setWaveInputValue] = React.useState(0);
    const [feet, setFeet] = React.useState(0);
    const [inches, setInches] = React.useState(0);
    const [meters, setMeters] = React.useState(0);
    const [cm, setCM] = React.useState(0);
    const c = 299792458;

    // Reduce the full wavelength by the multiplier.
    const lengths = [
        {name: '½ Antenna Length', multiplier: 0.5},
        {name: '¼ Antenna Length', multiplier: 0.25},
        {name: '⅝ Antenna Length', multiplier: 0.625},
    ];

    React.useEffect(() => {
        // Calculate full wavelength.
        const newFeet = 936 / mhz;
        setFeet(newFeet);
        setInches(newFeet * 12);
        setMeters(newFeet * 0.3048);
        setCM(newFeet * 0.3048 * 100);
        setWaveInputValue(roundDigits(c / (mhz * 1e6)));
    }, [mhz]);

    React.useEffect(() => {
        if (wave && parseFloat(wave) > 0) {
            setMhzInputValue(roundDigits(c / parseFloat(wave) / 1e6));
        }
    }, [wave])

    const mhzStorageKey = 'dipole_mhz';
    const storageMhzValue = localStorage.getItem(mhzStorageKey);
    React.useEffect(() => {
        if (storageMhzValue) {
            setMhz(parseFloat(storageMhzValue));
            setMhzInputValue(storageMhzValue);
        }
    }, []);

    const handleMhzChange = (e, {value}) => {
        setMhzInputValue(value);
        setMhz(value && parseFloat(value) > 0 ? parseFloat(value) : 0);
        localStorage.setItem(mhzStorageKey, value);
    }

    const handleWaveChange = (e, {value}) => {
        setWaveInputValue(value);
        setWave(value && parseFloat(value) > 0 ? parseFloat(value) : 0);
    }

    const [mhzSelected, setMhzSelected] = React.useState(true);
    const handleClick = (e, name) => {
        if (name === 'mhz') {
            setMhzSelected(true);
        } else {
            setMhzSelected(false);
        }
    }

    return <>
        <Header as='h2'>Dipole Antenna</Header>

        <Grid columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <ColoredInput fluid
                                  label='MHz'
                                  labelPosition='right'
                                  value={mhzInputValue}
                                  onChange={handleMhzChange}
                                  onSelect={e => handleClick(e, 'mhz')}
                                  color={mhzSelected ? null : 'grey'}
                    />
                </Grid.Column>
                <Grid.Column>
                    <ColoredInput fluid
                                  label='Wavelength'
                                  labelPosition='right'
                                  value={waveInputValue}
                                  onChange={handleWaveChange}
                                  onSelect={e => handleClick(e, 'wave')}
                                  color={mhzSelected ? 'grey' : null}
                    />
                </Grid.Column>
            </Grid.Row>
        </Grid>

        {lengths.map(i => {
            const [feet_, inches_] = convertFeetToFeetAndInches(feet * i.multiplier);
            const [half_feet, half_inches] = convertFeetToFeetAndInches(feet * i.multiplier / 2);
            return <Table key={i.name} size='large' striped unstackable>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell>{i.name}</TableHeaderCell>
                        <TableHeaderCell>Leg Length</TableHeaderCell>
                    </TableRow>
                </TableHeader>

                <TableBody>
                    <TableRow>
                        <TableCell>
                            {feet_} ft. {inches_} in.
                        </TableCell>
                        <TableCell>
                            {half_feet} ft. {half_inches} in.
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(inches * i.multiplier)} inches
                        </TableCell>
                        <TableCell>
                            {roundDigits(inches * i.multiplier / 2)} inches
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(meters * i.multiplier)} meters
                        </TableCell>
                        <TableCell>
                            {roundDigits(meters * i.multiplier / 2)} meters
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                            {roundDigits(cm * i.multiplier)} cm.
                        </TableCell>
                        <TableCell>
                            {roundDigits(cm * i.multiplier / 2)} cm.
                        </TableCell>
                    </TableRow>
                </TableBody>
            </Table>
        })}
    </>
}