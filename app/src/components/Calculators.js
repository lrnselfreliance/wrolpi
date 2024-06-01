import React from "react";
import {BackButton, roundDigits, useTitle} from "./Common";
import {Button, Header, Icon} from "./Theme";
import {GridColumn, GridRow, Input} from "semantic-ui-react";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {useCalcQuery} from "../hooks/customHooks";
import {ColoredInput} from "./Apps";

function TemperatureCalculator() {
    const [state, setState] = React.useState({
        celsius: '',
        fahrenheit: '',
        kelvin: '',
    })

    const handleInputChange = (e, {name, value}) => {
        if (value === '') {
            // User has cleared the input;
            setState({volt: '', ohm: '', amp: ''});
            return
        }

        const numValue = parseFloat(value.endsWith('.') ? `${value}0` : value);
        console.debug(`Calculating ${value} ${name}`);
        let newCelsius;
        let newKelvin;
        let newFahrenheit;
        if (name === 'fahrenheit') {
            newFahrenheit = value;
            newCelsius = roundDigits((numValue - 32) / 1.8);
            newKelvin = roundDigits(newCelsius + 273.15);
        } else if (name === 'celsius') {
            newCelsius = value;
            newFahrenheit = roundDigits((numValue * 1.8) + 32);
            newKelvin = roundDigits(numValue + 273.15);
        } else if (name === 'kelvin') {
            newKelvin = value;
            newCelsius = roundDigits(numValue - 273.15);
            newFahrenheit = roundDigits((newCelsius * 1.8) + 32);
        }
        setState({
            celsius: newCelsius,
            fahrenheit: newFahrenheit,
            kelvin: newKelvin
        });
    }

    const handleClick = (e) => {
        e.target.select();
    }

    const commonInputProps = {
        fluid: true,
        labelPosition: 'right',
        type: 'number',
        onChange: handleInputChange,
        onClick: handleClick
    };

    return <Grid columns={3}>
        <GridRow>
            <GridColumn>
                <Input value={state.celsius} label='°C' name='celsius' {...commonInputProps}/>
            </GridColumn>
            <GridColumn>
                <Input value={state.fahrenheit} label='°F' name='fahrenheit' {...commonInputProps}/>
            </GridColumn>
            <GridColumn>
                <Input value={state.kelvin} label='K' name='kelvin' {...commonInputProps}/>
            </GridColumn>
        </GridRow>
    </Grid>
}

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
    let newLastUpdated = lastUpdated;
    if (lastUpdated.length === 0) {
        newLastUpdated = [type];
    } else if (lastUpdated.length === 1 && lastUpdated[0] !== type) {
        newLastUpdated = [...lastUpdated, type];
    } else if (lastUpdated.length > 1 && lastUpdated[1] !== type) {
        newLastUpdated = [lastUpdated[1], type];
    }

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

function ElectricalCalculator() {
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
    };

    return <div>
        <Header as='h4'>Ohm's Law</Header>
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

export function CalculatorsPage() {
    const {calc, setCalc} = useCalcQuery();

    const calculators = [
        {key: 'temperature', icon: 'thermometer', button: 'Temperature', contents: <TemperatureCalculator/>},
        {key: 'electrical', icon: 'lightning', button: 'Electrical', contents: <ElectricalCalculator/>},
    ];

    const activeCalculator = calc ?
        calculators.filter(i => i.key === calc)[0]
        : null;
    const {button, title, contents} = activeCalculator || {};

    const name = title || button + ' Calculator';
    const header = activeCalculator ? name : 'Calculators';
    useTitle(header);

    const calculatorButtons = calculators.map(i => {
        const {button, icon, key} = i;
        return <Button key={key} onClick={() => setCalc(i.key)}>
            {icon && <Icon name={i.icon}/>}
            {button}
        </Button>
    });

    const body = activeCalculator ? <>
            <BackButton style={{marginBottom: '1em'}}/>
            <span>{contents}</span>
        </>
        : calculatorButtons;

    // TODO add Breadcrumb here.
    return <>
        <Header>{header}</Header>
        {body}
    </>
}
