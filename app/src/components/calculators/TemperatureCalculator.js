import React from "react";
import {roundDigits} from "../Common";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {GridColumn, GridRow, Input} from "semantic-ui-react";

export function TemperatureCalculator() {
    const [state, setState] = React.useState({
        celsius: '',
        fahrenheit: '',
        kelvin: '',
    })

    const handleInputChange = (e, {name, value}) => {
        if (value === '') {
            // User has cleared the input;
            setState({celsius: '', fahrenheit: '', kelvin: ''});
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
        if (newFahrenheit < -459.67) {
            console.warn('Temperature was below absolute zero!');
            newCelsius = -273.3;
            newFahrenheit = -459.67;
            newKelvin = 0;
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
