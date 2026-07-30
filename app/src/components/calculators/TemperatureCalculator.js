import React from "react";
import {roundDigits} from "../Common";
import {Grid, NumberInput} from "../ui";

export function TemperatureCalculator() {
    const [state, setState] = React.useState({
        celsius: '',
        fahrenheit: '',
        kelvin: '',
    })

    const handleInputChange = (name, value) => {
        if (value === '' || value === undefined || value === null) {
            // User has cleared the input;
            setState({celsius: '', fahrenheit: '', kelvin: ''});
            return
        }

        const stringValue = `${value}`;
        const numValue = parseFloat(stringValue.endsWith('.') ? `${stringValue}0` : stringValue);
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

    return <Grid>
        <Grid.Col span={4}>
            <NumberInput
                value={state.celsius}
                rightSection='°C'
                onChange={value => handleInputChange('celsius', value)}
                onClick={handleClick}
            />
        </Grid.Col>
        <Grid.Col span={4}>
            <NumberInput
                value={state.fahrenheit}
                rightSection='°F'
                onChange={value => handleInputChange('fahrenheit', value)}
                onClick={handleClick}
            />
        </Grid.Col>
        <Grid.Col span={4}>
            <NumberInput
                value={state.kelvin}
                rightSection='K'
                onChange={value => handleInputChange('kelvin', value)}
                onClick={handleClick}
            />
        </Grid.Col>
    </Grid>
}
