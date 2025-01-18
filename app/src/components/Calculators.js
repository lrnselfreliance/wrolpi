import React from "react";
import {Breadcrumbs, useTitle} from "./Common";
import {Button, Icon} from "./Theme";
import {useCalcQuery} from "../hooks/customHooks";
import {TemperatureCalculator} from "./calculators/TemperatureCalculator";
import {ElectricalCalculators} from "./calculators/ElectricalCalculators";
import {DipoleAntennaCalculator} from "./calculators/HamCalculators";
import {Link} from "react-router-dom";
import {RatioCalculators} from "./calculators/RatioCalculator";

export function CalculatorsPage() {
    const {calc, setCalc} = useCalcQuery();

    const calculators = [
        {key: 'electrical', icon: 'lightning', button: 'Electrical', contents: <ElectricalCalculators/>},
        {key: 'antenna', icon: 'signal', button: 'Antenna', contents: <DipoleAntennaCalculator/>},
        {key: 'temperature', icon: 'thermometer', button: 'Temperature', contents: <TemperatureCalculator/>},
        {key: ' ratio', icon: 'th large', button: 'Ratio', contents: <RatioCalculators/>},
    ];

    const activeCalculator = calc ?
        calculators.filter(i => i.key === calc)[0]
        : null;
    const {icon, button, title, contents} = activeCalculator || {};

    const name = activeCalculator ? title || button + ' Calculator' : 'Calculators';
    useTitle(name);

    const calculatorButtons = calculators.map(i => {
        const {button, icon, key} = i;
        return <Link key={key} to={`/more/calculators?calc=${key}`}>
            <Button style={{margin: '0.5em'}}>
                {icon && <Icon name={icon}/>}
                {button}
            </Button>
        </Link>
    });

    const body = activeCalculator ? <span>{contents}</span> : calculatorButtons;

    // Make first breadcrumb a link back to Calculators only when a calculator is active.
    const crumbs = activeCalculator
        ? [{text: 'Calculators', link: '/more/calculators'}, {text: name, icon: icon}]
        : [{text: 'Calculators'}];

    return <>
        <Breadcrumbs crumbs={crumbs} size='huge'/>

        <div style={{marginTop: '1em'}}>
            {body}
        </div>
    </>
}
