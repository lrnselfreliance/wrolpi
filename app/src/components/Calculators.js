import React from "react";
import {BackButton, useTitle} from "./Common";
import {Button, Header, Icon} from "./Theme";
import {useCalcQuery} from "../hooks/customHooks";
import {TemperatureCalculator} from "./calculators/TemperatureCalculator";
import {ElectricalCalculator} from "./calculators/ElectricalCalculators";
import {DipoleAntennaCalculator} from "./calculators/HamCalculators";

export function CalculatorsPage() {
    const {calc, setCalc} = useCalcQuery();

    const calculators = [
        {key: 'temperature', icon: 'thermometer', button: 'Temperature', contents: <TemperatureCalculator/>},
        {key: 'electrical', icon: 'lightning', button: 'Electrical', contents: <ElectricalCalculator/>},
        {key: 'antenna', icon: 'signal', button: 'Antenna', contents: <DipoleAntennaCalculator/>},
    ];

    const activeCalculator = calc ?
        calculators.filter(i => i.key === calc)[0]
        : null;
    const {icon, button, title, contents} = activeCalculator || {};

    const name = activeCalculator ? title || button + ' Calculator' : 'Calculators';
    const header = activeCalculator ? <Header><Icon name={icon}/>{name}</Header> : <Header>{name}</Header>;
    useTitle(name);

    const calculatorButtons = calculators.map(i => {
        const {button, icon, key} = i;
        return <Button key={key} onClick={() => setCalc(key)}>
            {icon && <Icon name={icon}/>}
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
        {header}
        {body}
    </>
}
