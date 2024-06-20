import {roundDigits} from "../Common";
import React from "react";
import {Header} from "../Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {GridColumn, GridRow} from "semantic-ui-react";
import {ColoredInput} from "../Apps";

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

export function ElectricalCalculator() {
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
