import React from "react";
import {Breadcrumbs, useTitle} from "./Common";
import {Button, Header, Icon} from "./Theme";
import {useCalcQuery} from "../hooks/customHooks";
import {TemperatureCalculator} from "./calculators/TemperatureCalculator";
import {ElectricalCalculators} from "./calculators/ElectricalCalculators";
import {DipoleAntennaCalculator} from "./calculators/HamCalculators";
import {Link} from "react-router";
import {RatioCalculators} from "./calculators/RatioCalculator";
import {QRCodeCalculator} from "./calculators/QRCodeCalculator";
import {DriveCalculator} from "./calculators/DriveCalculator";
import {WaterCalculator} from "./calculators/WaterCalculator";
import {FoodStorageCalculator} from "./calculators/FoodStorageCalculator";
import {OneTimePadCalculator} from "./calculators/OneTimePadCalculator";
import {VinDecoderCalculator} from "./calculators/VinDecoderCalculator";

// Calculators are shown in these titled groups, in this order.  Each calculator carries a
// `group` matching one of these names; any calculator whose group is missing/unknown falls
// into a trailing "Other" section so a new calculator can never silently disappear.
//
// `color` is a Semantic UI named color (colorblind-friendly palette) used to tint the group's
// buttons.  Violet is intentionally avoided — it is the default navbar color and would blend in.
export const CALCULATOR_GROUPS = [
    {name: 'Preparedness & Storage', color: 'red'},
    {name: 'Radio & Communications', color: 'blue'},
    {name: 'Engineering', color: 'yellow'},
    {name: 'Tools & Reference', color: 'grey'},
];

export const useCalculators = () => {
    const [calc, setCalc] = useCalcQuery();

    const calculators = [
        {key: 'ratio', icon: 'th large', button: 'Ratio', group: 'Engineering', contents: <RatioCalculators/>},
        {key: 'electrical', icon: 'lightning', button: 'Electrical', group: 'Engineering', contents: <ElectricalCalculators/>},
        {key: 'drive', icon: 'cogs', button: 'Drive Ratio', group: 'Engineering', contents: <DriveCalculator/>},
        {key: 'water', icon: 'tint', button: 'Water Storage', group: 'Preparedness & Storage', contents: <WaterCalculator/>},
        {key: 'ration', icon: 'food', button: 'Food Storage', group: 'Preparedness & Storage', contents: <FoodStorageCalculator/>},
        {key: 'antenna', icon: 'signal', button: 'Antenna', group: 'Radio & Communications', contents: <DipoleAntennaCalculator/>},
        {key: 'temperature', icon: 'thermometer', button: 'Temperature', group: 'Tools & Reference', contents: <TemperatureCalculator/>},
        {key: 'qrCode', icon: 'qrcode', button: 'QR Code', group: 'Tools & Reference', contents: <QRCodeCalculator/>},
        {key: 'otp', icon: 'lock', button: 'One Time Pad', title: 'One Time Pad', group: 'Radio & Communications', contents: <OneTimePadCalculator/>},
        {key: 'vin', icon: 'car', button: 'VIN Decoder', title: 'VIN Decoder', group: 'Tools & Reference', contents: <VinDecoderCalculator/>},
    ];

    const activeCalculator = calc ? calculators.find(i => i.key === calc) : null;

    const calculatorButton = ({button, icon, key}, color) =>
        <Link key={key} to={`/more/calculators?calc=${key}`}>
            <Button color={color} style={{margin: '0.5em'}}>
                {icon && <Icon name={icon}/>}
                {button}
            </Button>
        </Link>;

    // Render each defined group as a titled section, then any leftovers under "Other".
    const groupNames = CALCULATOR_GROUPS.map(g => g.name);
    const grouped = CALCULATOR_GROUPS.map(g => [g.name, g.color, calculators.filter(c => c.group === g.name)]);
    const leftovers = calculators.filter(c => !groupNames.includes(c.group));
    if (leftovers.length > 0) {
        grouped.push(['Other', undefined, leftovers]);
    }

    const calculatorLinks = grouped
        .filter(([, , items]) => items.length > 0)
        .map(([name, color, items]) =>
            <div key={name} style={{marginBottom: '1.5em'}}>
                <Header as='h3'>{name}</Header>
                {items.map(c => calculatorButton(c, color))}
            </div>);

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
