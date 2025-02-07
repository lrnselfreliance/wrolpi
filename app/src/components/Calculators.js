import React from "react";
import {Breadcrumbs, useTitle} from "./Common";
import {Button, Icon} from "./Theme";
import {useCalcQuery} from "../hooks/customHooks";
import {TemperatureCalculator} from "./calculators/TemperatureCalculator";
import {ElectricalCalculators} from "./calculators/ElectricalCalculators";
import {DipoleAntennaCalculator} from "./calculators/HamCalculators";
import {Link} from "react-router-dom";
import {RatioCalculators} from "./calculators/RatioCalculator";
import {QRCodeCalculator} from "./calculators/QRCodeCalculator";

export const useCalculators = () => {
    const [calc, setCalc] = useCalcQuery();

    const calculators = [
        {key: 'ratio', icon: 'th large', button: 'Ratio', contents: <RatioCalculators/>},
        {key: 'electrical', icon: 'lightning', button: 'Electrical', contents: <ElectricalCalculators/>},
        {key: 'antenna', icon: 'signal', button: 'Antenna', contents: <DipoleAntennaCalculator/>},
        {key: 'temperature', icon: 'thermometer', button: 'Temperature', contents: <TemperatureCalculator/>},
        {key: 'qrCode', icon: 'qrcode', button: 'QR Code', contents: <QRCodeCalculator/>},
    ];

    const activeCalculator = calc ? calculators.find(i => i.key === calc) : null;

    const calculatorLinks = calculators.map(i => {
        const {button, icon, key} = i;
        return <Link key={key} to={`/more/calculators?calc=${key}`}>
            <Button key={key} style={{margin: '0.5em'}}>
                {icon && <Icon name={icon}/>}
                {button}
            </Button>
        </Link>
    });

    return {calc, calculators, activeCalculator, calculatorLinks}
}

export function CalculatorsPage() {
    const {activeCalculator, calculatorLinks} = useCalculators();

    const {icon, button, title, contents} = activeCalculator || {};
    const name = activeCalculator ? title || button + ' Calculator' : 'Calculators';
    useTitle(name);

    const body = activeCalculator ? <span>{contents}</span> : calculatorLinks;

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
