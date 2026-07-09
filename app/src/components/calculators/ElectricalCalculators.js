import {InfoPopup, roundDigits, Toggle, useLocalStorage, useLocalStorageInt} from "../Common";
import React, {useState} from "react";
import {Form, Header, Segment, Table} from "../Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {
    Container,
    Dropdown,
    GridColumn,
    GridRow,
    Icon,
    Input,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow,
} from "semantic-ui-react";
import {ColoredInput} from "../Apps";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {Media, ThemeContext} from "../../contexts/contexts";

const initialState = {
    volts: '',
    amps: '',
    ohms: '',
    watts: '',
    lastUpdated: [],
};

// Ohms Law functions.  These take two values, and return the other two electrical values.
const voltsAmps = (volts, amps) => {
    const watts = volts * amps;
    const ohms = volts / amps;
    return [roundDigits(watts) || 0, roundDigits(ohms) || 0]
};
const voltsOhms = (volts, ohms) => {
    const amps = volts / ohms;
    const watts = volts * amps;
    return [roundDigits(amps) || 0, roundDigits(watts) || 0]
};
const ampsOhms = (amps, ohms) => {
    const volts = amps * ohms;
    const watts = volts * amps;
    return [roundDigits(volts) || 0, roundDigits(watts) || 0]
};
const voltsWatts = (volts, watts) => {
    const amps = watts / volts;
    const ohms = volts / amps;
    return [roundDigits(amps) || 0, roundDigits(ohms) || 0]
};
const ampsWatts = (amps, watts) => {
    const volts = watts / amps;
    const ohms = volts / amps;
    return [roundDigits(volts) || 0, roundDigits(ohms) || 0]
};
const wattsOhms = (watts, ohms) => {
    const volts = Math.sqrt(watts * ohms);
    const amps = volts / ohms;
    return [roundDigits(volts), roundDigits(amps)]
};

function ohmsLawReducer(state, action) {
    const {type, value} = action;
    let {volts, amps, ohms, watts, lastUpdated} = state;

    // Only replace last updated when a different input was updated.
    let newLastUpdated = lastUpdated || [];
    newLastUpdated = newLastUpdated.filter(i => i !== type);
    newLastUpdated = [type, ...newLastUpdated];
    newLastUpdated = newLastUpdated.slice(0, 2);

    // Copy new value into it's respective state.  Do not allow negative numbers.
    if (type === 'amps') {
        amps = Math.abs(value);
    } else if (type === 'volts') {
        volts = Math.abs(value);
    } else if (type === 'ohms') {
        ohms = Math.abs(value);
    } else if (type === 'watts') {
        watts = Math.abs(value);
    }

    // Sort the updated values, so we don't have to define everything twice.
    const sortedLastUpdated = [...newLastUpdated].sort().join(',');
    switch (sortedLastUpdated) {
        case 'amps,ohms':
            [volts, watts] = ampsOhms(amps, ohms);
            break;
        case 'amps,volts':
            [watts, ohms] = voltsAmps(volts, amps);
            break;
        case 'amps,watts':
            [volts, ohms] = ampsWatts(amps, watts);
            break;
        case 'ohms,volts':
            [amps, watts] = voltsOhms(volts, ohms);
            break;
        case 'ohms,watts':
            [volts, amps] = wattsOhms(watts, ohms);
            break;
        case 'volts,watts':
            [amps, ohms] = voltsWatts(volts, watts);
            break;
    }

    return {volts, amps, ohms, watts, lastUpdated: newLastUpdated};
}

export function OhmsLawCalculator({setVolts}) {
    // Provides a form which provides 4 inputs (volts, amps, ohms, watts), and calculates the missing values.

    const [state, dispatch] = React.useReducer(ohmsLawReducer, initialState);

    const calculateColor = (name) => {
        // Recently updated inputs are white, others are grey.
        return state.lastUpdated.indexOf(name) >= 0 ? null : 'grey';
    }

    const inputProps = {
        fluid: true,
        type: 'number',
        labelPosition: 'right',
        onSelect: e => e.target.select(), // Select the contents of the Input when a user selects it.
        autoComplete: 'off',
    };

    React.useEffect(() => {
        console.log(state);
        if (state.volts > 0) {
            setVolts(state.volts);
        }
    }, [state]);

    return <div>
        <Header as='h1'>Ohm's Law</Header>
        <Grid columns={2}>
            <GridRow>
                <GridColumn>
                    <ColoredInput {...inputProps}
                                  value={state.volts}
                                  onChange={e => dispatch({type: 'volts', value: e.target.value})}
                                  label='Volts'
                                  color={calculateColor('volts')}
                    />
                </GridColumn>
                <GridColumn>
                    <ColoredInput {...inputProps}
                                  value={state.amps}
                                  onChange={e => dispatch({type: 'amps', value: e.target.value})}
                                  label='Amps'
                                  color={calculateColor('amps')}
                    />
                </GridColumn>
            </GridRow>
            <GridRow>
                <GridColumn>
                    <ColoredInput {...inputProps}
                                  value={state.ohms}
                                  onChange={e => dispatch({type: 'ohms', value: e.target.value})}
                                  label='Ohms'
                                  color={calculateColor('ohms')}
                    />
                </GridColumn>
                <GridColumn>
                    <ColoredInput {...inputProps}
                                  value={state.watts}
                                  onChange={e => dispatch({type: 'watts', value: e.target.value})}
                                  label='Watts'
                                  color={calculateColor('watts')}
                    />
                </GridColumn>
            </GridRow>
        </Grid>
    </div>
}

// Dropdown options for wire types
export const resistancesPerKFeet = {
    solid: {
        '0000 AWG': 0.049,
        '00 AWG': 0.0779,
        '0 AWG': 0.0982,
        '2 AWG': 0.1563,
        '4 AWG': 0.2485,
        '6 AWG': 0.3951,
        '8 AWG': 0.628,
        '10 AWG': 0.9987,
        '12 AWG': 1.588,
        '14 AWG': 2.525,
        '16 AWG': 4.015,
        '20 AWG': 10.15,
        '24 AWG': 25.67,
    },
    stranded: {
        '0000 AWG': 0.0608,
        '00 AWG': 0.0967,
        '0 AWG': 0.122,
        '2 AWG': 0.194,
        '4 AWG': 0.308,
        '6 AWG': 0.491,
        '8 AWG': 0.778,
        '10 AWG': 1.24,
        '12 AWG': 1.98,
        '14 AWG': 3.14,
        '16 AWG': 4.99,
        '18 AWG': 7.95,
    },
    solid_aluminum: {
        '0000 AWG': 0.0804,
        '00 AWG': 0.128,
        '0 AWG': 0.161,
        '2 AWG': 0.256,
        '4 AWG': 0.408,
        '6 AWG': 0.648,
        '8 AWG': 1.03,
        '10 AWG': 1.64,
        '12 AWG': 2.61,
        '14 AWG': 4.14,
        '16 AWG': 6.59,
        '20 AWG': 16.7,
        '24 AWG': 42.1,
    },
    stranded_aluminum: {
        '0000 AWG': 0.082,
        '00 AWG': 0.130,
        '0 AWG': 0.164,
        '2 AWG': 0.261,
        '4 AWG': 0.416,
        '6 AWG': 0.661,
        '8 AWG': 1.05,
        '10 AWG': 1.67,
        '12 AWG': 2.66,
        '14 AWG': 4.22,
        '16 AWG': 6.72,
        '18 AWG': 10.7,
    },
};
export const resistancesPerKm = {
    solid: {
        ['120 mm²']: 0.153,
        ['70 mm²']: 0.272,
        ['50 mm²']: 0.391,
        ['25 mm²']: 0.734,
        ['16 mm²']: 1.16,
        ['10 mm²']: 1.84,
        ['6 mm²']: 3.11,
        ['4 mm²']: 4.70,
        ['2.5 mm²']: 7.56,
        ['1.5 mm²']: 12.3,
        ['1 mm²']: 18.5,
        ['0.75 mm²']: 25.0,
        ['0.5 mm²']: 37.0
    },
    stranded: {
        ['120 mm²']: 0.150,
        ['70 mm²']: 0.268,
        ['50 mm²']: 0.387,
        ['25 mm²']: 0.727,
        ['16 mm²']: 1.15,
        ['10 mm²']: 1.83,
        ['6 mm²']: 3.08,
        ['4 mm²']: 4.61,
        ['2.5 mm²']: 7.41,
        ['1.5 mm²']: 12.1,
        ['1 mm²']: 18.1,
        ['0.75 mm²']: 24.5,
        ['0.5 mm²']: 36.0
    },
    solid_aluminum: {
        ['120 mm²']: 0.235,
        ['70 mm²']: 0.403,
        ['50 mm²']: 0.564,
        ['25 mm²']: 1.13,
        ['16 mm²']: 1.76,
        ['10 mm²']: 2.82,
        ['6 mm²']: 4.70,
        ['4 mm²']: 7.05,
        ['2.5 mm²']: 11.3,
        ['1.5 mm²']: 18.8,
        ['1 mm²']: 28.2,
        ['0.75 mm²']: 37.6,
        ['0.5 mm²']: 56.4
    },
    stranded_aluminum: {
        ['120 mm²']: 0.240,
        ['70 mm²']: 0.411,
        ['50 mm²']: 0.575,
        ['25 mm²']: 1.15,
        ['16 mm²']: 1.80,
        ['10 mm²']: 2.88,
        ['6 mm²']: 4.79,
        ['4 mm²']: 7.19,
        ['2.5 mm²']: 11.5,
        ['1.5 mm²']: 19.2,
        ['1 mm²']: 28.8,
        ['0.75 mm²']: 38.4,
        ['0.5 mm²']: 57.5
    }
};


// Dropdown options for wire types
const wireTypeOptions = [
    {key: 'solid', text: 'Solid Copper', value: 'solid'},
    {key: 'stranded', text: 'Stranded Copper', value: 'stranded'},
    {key: 'solid_aluminum', text: 'Solid Aluminum', value: 'solid_aluminum'},
    {key: 'stranded_aluminum', text: 'Stranded Aluminum', value: 'stranded_aluminum'},
];

// Helper function to calculate power loss
export const calcPowerLossPercent = (isSAE, volts, amps, resistancePerKiloLength, length) => {
    if (volts <= 0) {
        return 0; // Avoid division by zero and meaningless calculations when there's no voltage.
    }

    const resistancePerLength = resistancePerKiloLength / 1000;
    // Double the length for return trip.
    const resistance = 2 * length * resistancePerLength;
    // console.log(`resistancePerFoot=${resistancePerFoot} resistance=${resistance}`)
    const voltageDrop = amps * resistance;

    return (voltageDrop / volts) * 100; // Return as a percentage
};

const PowerLossCalculator = ({volts, setVolts, wireType, setWireType, isSAE, setIsSAE, length, setLength}) => {
    const [ampsRange] = useState([1, 5, 10, 20, 40, 100]);

    const {inverted} = React.useContext(ThemeContext);
    const warningBackgroundColor = inverted === 'inverted' ? '#332020' : '#ffbebe';

    const resistances = isSAE ? resistancesPerKFeet[wireType]
        : resistancesPerKm[wireType];

    const voltsInput = <Input fluid
                              label='Volts'
                              labelPosition='right'
                              type='number'
                              value={volts}
                              onChange={(e, {value}) => setVolts(parseInt(value))}
                              autoComplete="off"
    />;

    const saeToggle = <Toggle
        label={isSAE ? 'SAE' : 'IEC'}
        checked={isSAE}
        onChange={() => setIsSAE(!isSAE)}
    />;

    const lengthInput = <Grid columns={2}>
        <Grid.Row>
            <Grid.Column mobile={12} tablet={12}>
                <Input fluid
                       label={isSAE ? 'feet' : 'meters'}
                       labelPosition='right'
                       type='number'
                       value={length}
                       onChange={(e, {value}) => setLength(parseInt(value))}
                       autoComplete="off"
                />
            </Grid.Column>
            <Grid.Column mobile={4} tablet={2}>
                <InfoPopup
                    content='Length is one way.  This length will be doubled to account for return wire.'/>
            </Grid.Column>
        </Grid.Row>
    </Grid>;

    const wireTypeDropdown = <Dropdown
        placeholder='Select Wire Type'
        fluid
        selection
        options={wireTypeOptions}
        value={wireType}
        onChange={(e, {value}) => setWireType(value)}
    />;
    return <Form>
        <Header as='h1'>Power Loss</Header>
        <Media at='mobile'>
            <Grid columns={2} divided stackable>
                <Grid.Row>
                    <Grid.Column>{voltsInput}</Grid.Column>
                    <Grid.Column>{lengthInput}</Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column>{wireTypeDropdown}</Grid.Column>
                    <Grid.Column>{saeToggle}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media greaterThan='mobile'>
            <Grid columns={2} divided>
                <Grid.Row>
                    <Grid.Column>{voltsInput}</Grid.Column>
                    <Grid.Column>{saeToggle}</Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column>{lengthInput}</Grid.Column>
                    <Grid.Column>{wireTypeDropdown}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>

        <Table unstackable compact celled definition>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell/>
                    {ampsRange.map(amp => <TableHeaderCell key={amp}>{amp}A</TableHeaderCell>)}
                </TableRow>
            </TableHeader>
            <TableBody>
                {Object.entries(resistances).map(([size, resistence]) => (
                    <TableRow key={size}>
                        <TableCell>{size}</TableCell>
                        {ampsRange.map(amp => {
                            const lossPercentage = calcPowerLossPercent(isSAE, volts, amp, resistence, length);
                            const style = lossPercentage > 2 ? {backgroundColor: warningBackgroundColor} : null;
                            return <TableCell key={`${size}-${amp}`} style={style}>
                                {lossPercentage >= 100 ? '-' : roundDigits(lossPercentage, 1) + '%'}
                            </TableCell>
                        })}
                    </TableRow>
                ))}
            </TableBody>
        </Table>

        <Message icon color='yellow'>
            <Icon name='exclamation'/>
            <Message.Content>
                <Message.Header>Warning</Message.Header>
                These numbers are only an estimate and are only applicable for bare wires.
            </Message.Content>
        </Message>
    </Form>
};

// Resistance changes with temperature; the resistance tables are referenced at 20°C.
export const COPPER_TEMP_COEFFICIENT = 0.00393; // per °C
export const ALUMINUM_TEMP_COEFFICIENT = 0.00403; // per °C
const REFERENCE_TEMPERATURE_C = 20;

const tempCoefficientForWireType = (wireType) =>
    wireType.includes('aluminum') ? ALUMINUM_TEMP_COEFFICIENT : COPPER_TEMP_COEFFICIENT;

// Helper function to calculate the expected millivolt drop across a single wire (4-wire Kelvin measurement).
export const calcKelvinMilliVoltDrop = (amps, resistancePerKiloLength, length,
                                        temperatureC = REFERENCE_TEMPERATURE_C,
                                        tempCoefficient = COPPER_TEMP_COEFFICIENT) => {
    const temperatureFactor = 1 + tempCoefficient * (temperatureC - REFERENCE_TEMPERATURE_C);
    const resistancePerLength = (resistancePerKiloLength * temperatureFactor) / 1000;
    // Sense leads measure across the single conductor, so the length is NOT doubled.
    const resistance = length * resistancePerLength;
    return amps * resistance * 1000; // Volts to millivolts.
};

const FourWireKelvinCalculator = ({wireType, isSAE, length}) => {
    const [ampsRange] = useState([1, 5, 10]);
    // Stored in Celsius; displayed in Fahrenheit when SAE.  Default is room temperature.
    const decodeTemperature = (value) => {
        const temperature = parseFloat(value);
        return Number.isFinite(temperature) ? temperature : REFERENCE_TEMPERATURE_C;
    };
    const [temperatureC, setTemperatureC] = useLocalStorage(
        'calculators.kelvin.temperature_c', REFERENCE_TEMPERATURE_C, decodeTemperature, (num) => num.toString());

    const resistances = isSAE ? resistancesPerKFeet[wireType]
        : resistancesPerKm[wireType];

    const displayTemperature = isSAE ? roundDigits(temperatureC * 9 / 5 + 32, 1) : roundDigits(temperatureC, 1);
    const handleTemperatureChange = (value) => {
        if (value === '') {
            // Never store NaN; fall back to room temperature when the input is cleared.
            setTemperatureC(REFERENCE_TEMPERATURE_C);
            return;
        }
        const temperature = parseFloat(value);
        if (!Number.isFinite(temperature)) {
            return;
        }
        setTemperatureC(isSAE ? (temperature - 32) * 5 / 9 : temperature);
    };

    return <Form>
        <Header as='h1'>4-Wire Kelvin</Header>
        <p>
            Expected millivolt drop across {length} {isSAE ? 'feet' : 'meters'} of wire when driving a known
            current through it.  Measure with separate sense leads at each end of the wire.
            <InfoPopup
                content='Uses the length and wire type from the Power Loss calculator above.  The length is NOT doubled because the sense leads measure across a single conductor.'/>
        </p>

        <Grid columns={2}>
            <Grid.Row>
                <Grid.Column mobile={12} tablet={12}>
                    <Input fluid
                           label={isSAE ? '°F' : '°C'}
                           labelPosition='right'
                           type='number'
                           value={displayTemperature}
                           onChange={(e, {value}) => handleTemperatureChange(value)}
                           autoComplete="off"
                    />
                </Grid.Column>
                <Grid.Column mobile={4} tablet={2}>
                    <InfoPopup
                        content='Wire temperature.  Resistances are referenced at 20°C (68°F) and corrected using the temperature coefficient of the wire material (copper 0.393% per °C, aluminum 0.403% per °C).'/>
                </Grid.Column>
            </Grid.Row>
        </Grid>

        <Table unstackable compact celled definition>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell/>
                    {ampsRange.map(amp => <TableHeaderCell key={amp}>{amp}A</TableHeaderCell>)}
                </TableRow>
            </TableHeader>
            <TableBody>
                {Object.entries(resistances).map(([size, resistance]) => (
                    <TableRow key={size}>
                        <TableCell>{size}</TableCell>
                        {ampsRange.map(amp => {
                            const milliVolts = calcKelvinMilliVoltDrop(
                                amp, resistance, length, temperatureC, tempCoefficientForWireType(wireType));
                            return <TableCell key={`${size}-${amp}`}>
                                {roundDigits(milliVolts, 1)} mV
                            </TableCell>
                        })}
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    </Form>
};

export const ElectricalCalculators = () => {
    const [volts, setVolts] = useLocalStorageInt('calculators.electrical.volts', 120);
    const [wireType, setWireType] = useLocalStorage('calculators.power_loss.wire_type', 'solid');
    const [isSAE, setIsSAE] = useLocalStorage('calculators.power_loss.is_sae', true);
    const [length, setLength] = useLocalStorageInt('calculators.power_loss.length', 100);
    return <Container>
        <Segment><OhmsLawCalculator setVolts={setVolts}/></Segment>
        <Segment><PowerLossCalculator volts={volts} setVolts={setVolts}
                                      wireType={wireType} setWireType={setWireType}
                                      isSAE={isSAE} setIsSAE={setIsSAE}
                                      length={length} setLength={setLength}/></Segment>
        <Segment><FourWireKelvinCalculator wireType={wireType} isSAE={isSAE} length={length}/></Segment>
    </Container>
}
