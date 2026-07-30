import {Group, Header, Label, NumberInput, Select, Table} from "../ui";
import React from "react";
import {HandPointMessage, roundDigits, useLocalStorage} from "../Common";
import {createUnit, multiply, unit} from "mathjs";
import {Media} from "../../contexts/contexts";

// Used to calculate ratios without any units.
const nullUnit = createUnit('null');

function ratioReducer(prevState, e) {
    const {value, name} = 'target' in e ? e.target : e;
    let {a, aUnit, b, bUnit, c, cUnit, d, dUnit, base, lastUpdated, recentUnits} = prevState;

    // Keep a stack of which inputs are updated.  Limit it to the 3 most recent inputs.
    let newLastUpdated = lastUpdated || [];
    if (['a', 'b', 'c', 'd'].includes(name)) {
        newLastUpdated = newLastUpdated.filter(i => i !== name);
        newLastUpdated = [name, ...newLastUpdated];
        newLastUpdated = newLastUpdated.slice(0, 3);
    }

    // TODO handle disconnect and allow app install

    const calculateA = () => a = multiply(b, c).divide(d).to(aUnit);
    const calculateB = () => b = multiply(a, d).divide(c).to(bUnit);
    const calculateC = () => c = multiply(a, d).divide(b).to(cUnit);
    const calculateD = () => d = multiply(b, c).divide(a).to(dUnit);

    if (name === 'aUnit') {
        aUnit = value;
        a = a.to(value);
    } else if (name === 'bUnit') {
        bUnit = value;
        b = b.to(value);
    } else if (name === 'cUnit') {
        cUnit = value;
        c = c.to(value);
    } else if (name === 'dUnit') {
        dUnit = value;
        d = d.to(value);
    } else if (name === 'a') {
        recentUnits[base] = aUnit.toString(); // Convert to string for local storage.
        a = unit(value, aUnit);
    } else if (name === 'b') {
        recentUnits[base] = bUnit.toString();
        b = unit(value, bUnit);
    } else if (name === 'c') {
        recentUnits[base] = cUnit.toString();
        c = unit(value, cUnit);
    } else if (name === 'd') {
        recentUnits[base] = dUnit.toString();
        d = unit(value, dUnit);
    } else if (name === 'base') {
        // Base is changing, reset units and values.
        base = value;
        // Get the unit of this base that the user used most recently.
        aUnit = bUnit = cUnit = dUnit = recentUnits[base] || nullUnit;
        a = b = c = d = unit('', aUnit);
        // Reset last updated.
        newLastUpdated = [];
    }

    // Calculate ratio of the input which hasn't been updated recently.  But only if all other inputs have values.
    if (newLastUpdated.length === 3) {
        if (!newLastUpdated.includes('a')) {
            calculateA();
        } else if (!newLastUpdated.includes('b')) {
            calculateB();
        } else if (!newLastUpdated.includes('c')) {
            calculateC();
        } else if (!newLastUpdated.includes('d')) {
            calculateD();
        }
    }

    return {
        base,
        lastUpdated: newLastUpdated,
        a,
        b,
        c,
        d,
        aUnit,
        bUnit,
        cUnit,
        dUnit,
        recentUnits,
    }
}

const baseToUnitsMap = {
    'length': [
        {value: 'centimeter', text: 'centimeter'},
        {value: 'feet', text: 'feet'},
        {value: 'inch', text: 'inch'},
        {value: 'kilometer', text: 'kilometer'},
        {value: 'meter', text: 'meter'},
        {value: 'mile', text: 'mile'},
    ],
    'area': [
        {value: 'm2', text: 'm²'},
        {value: 'sqin', text: 'square inch'},
        {value: 'sqyd', text: 'square yard'},
        {value: 'sqmi', text: 'square mile'},
        {value: 'acre', text: 'acre'},
        {value: 'hectare', text: 'hectare'},
    ],
    'volume': [
        {value: 'cc', text: 'cc'},
        {value: 'liter', text: 'liter'},
        {value: 'm3', text: 'meters³'},
        {value: 'cup', text: 'cup'},
        {value: 'fluidounce', text: 'fl.oz'},
        {value: 'gallon', text: 'gallon'},
        {value: 'quart', text: 'quart'},
        {value: 'milliliter', text: 'ml'},
        {value: 'tablespoon', text: 'tablespoon'},
        {value: 'teaspoon', text: 'teaspoon'},
        {value: 'cuin', text: 'cuin'},
    ],
    'mass': [
        {value: 'grain', text: 'grain'},
        {value: 'gram', text: 'gram'},
        {value: 'lbs', text: 'pound'},
        {value: 'stone', text: 'stone'},
        {value: 'ton', text: 'ton'},
    ],
    'energy': [
        {value: 'joule', text: 'joule'},
        {value: 'Wh', text: 'Wh'},
        {value: 'BTU', text: 'BTU'},
        {value: 'watt', text: 'watt'},
        {value: 'hp', text: 'hp'},
    ],
};

// Used to get from unit like `BTU` back to the base `energy`.
let unitsToBaseMap = {};
for (const [base, units] of Object.entries(baseToUnitsMap)) {
    for (const {value} of units) {
        unitsToBaseMap[value] = base;
    }
}

const defaultUnits = {
    // These will be replaced using local storage.
    length: baseToUnitsMap.length[0]['value'], // centimeter
    area: baseToUnitsMap.area[0]['value'], // m2
    volume: baseToUnitsMap.volume[0]['value'], // cc
    mass: baseToUnitsMap.mass[0]['value'], // grain
    energy: baseToUnitsMap.energy[0]['value'], // joule
    [null]: null, // nullUnit
};

const initialState = {
    base: null,
    lastUpdated: [],
    a: unit('', nullUnit), // The value displayed to the user.
    b: unit('', nullUnit),
    c: unit('', nullUnit),
    d: unit('', nullUnit),
    aUnit: nullUnit,
    bUnit: nullUnit,
    cUnit: nullUnit,
    dUnit: nullUnit,
    recentUnits: defaultUnits,
};

const unitToInputValue = (u) => {
    const num = u.toNumber();
    if (num <= 0) {
        return ''
    }
    return roundDigits(num, 3)
}

// "None" is represented by an empty string in the Select (which needs a string value);
// the reducer still receives/produces `null` for the base, same as before migration.
const baseOptions = [
    {value: '', label: 'None'},
    {value: 'length', label: 'Length — meter, feet, inch, etc.'},
    {value: 'area', label: 'Area — inch², m², etc.'},
    {value: 'volume', label: 'Volume — liter, m³, cup, etc.'},
    {value: 'mass', label: 'Mass — gram, pound, etc.'},
    {value: 'energy', label: 'Energy — joule, watt, etc.'},
];

const RatioInput = React.forwardRef(({name, label, value, unitValue, unitName, unitOptions, color, dispatch, onKeyDown}, ref) => (
    <Group gap={0} wrap='nowrap' align='stretch' style={{marginBottom: '0.25em'}}>
        <Label color={color || 'grey'}>{label}</Label>
        <NumberInput
            id={name}
            name={name}
            ref={ref}
            value={unitToInputValue(value)}
            onChange={val => dispatch({name, value: val})}
            onKeyDown={onKeyDown}
            onFocus={e => e.target.select()}
            hideControls
            style={{flex: 1}}
        />
        {unitOptions &&
            <Select
                data={unitOptions.map(o => ({value: o.value, label: o.text}))}
                onChange={val => dispatch({name: unitName, value: val})}
                name={unitName}
                value={unitValue}
                style={{minWidth: 150}}
            />}
    </Group>
));

const RatioCalculator = () => {
    // Get the units the user recently used.  These will be set if the user changes the base.
    const [storageRecentUnits, setStorageRecentUnits] = useLocalStorage('ratio_calculator_recent_units',
        initialState.recentUnits);
    const [state, dispatch] = React.useReducer(
        ratioReducer,
        storageRecentUnits,
        (recentUnits) => ({...initialState, recentUnits})
    );

    // Overwrite the most recently used unit for each base.
    React.useEffect(() => {
        const updates = {};
        [state.aUnit, state.bUnit, state.cUnit, state.dUnit].forEach(unitValue => {
            const baseKey = unitsToBaseMap[unitValue];
            if (baseKey) {
                updates[baseKey] = unitValue;
            }
        });
        if (Object.keys(updates).length > 0) {
            setStorageRecentUnits(prev => ({...prev, ...updates}));
        }
    }, [state.aUnit, state.bUnit, state.cUnit, state.dUnit, setStorageRecentUnits]);

    const inputARef = React.useRef(null);
    const inputBRef = React.useRef(null);
    const inputCRef = React.useRef(null);
    const inputDRef = React.useRef(null);

    const unitOptions = baseToUnitsMap[state.base];

    // Recently-updated inputs (the ones the user is actively typing) are highlighted;
    // the others read as inactive/grey.
    const getColor = (name) => state.lastUpdated.includes(name) ? 'blue' : 'grey';

    const baseDropdown = <Select
        placeholder='Base Units'
        data={baseOptions}
        value={state.base ?? ''}
        name='base'
        onChange={val => dispatch({name: 'base', value: val || null})}
        style={{marginBottom: '1em'}}
    />;

    const handleInputChange = (e) => {
        // Allow the user to switch between inputs using a, b, c, and d keys.
        const refs = {a: inputARef, b: inputBRef, c: inputCRef, d: inputDRef};
        if (refs[e?.key]) {
            refs[e.key].current.focus();
        }
    };

    const inputA = <RatioInput
        ref={inputARef}
        name="a"
        label="A"
        value={state.a}
        unitValue={state.aUnit}
        unitName="aUnit"
        unitOptions={unitOptions}
        color={getColor('a')}
        dispatch={dispatch}
        onKeyDown={handleInputChange}
    />;

    const inputB = <RatioInput
        ref={inputBRef}
        name="b"
        label="B"
        value={state.b}
        unitValue={state.bUnit}
        unitName="bUnit"
        unitOptions={unitOptions}
        color={getColor('b')}
        dispatch={dispatch}
        onKeyDown={handleInputChange}
    />;

    const inputC = <RatioInput
        ref={inputCRef}
        name="c"
        label="C"
        value={state.c}
        unitValue={state.cUnit}
        unitName="cUnit"
        unitOptions={unitOptions}
        color={getColor('c')}
        dispatch={dispatch}
        onKeyDown={handleInputChange}
    />;

    const inputD = <RatioInput
        ref={inputDRef}
        name="d"
        label="D"
        value={state.d}
        unitValue={state.dUnit}
        unitName="dUnit"
        unitOptions={unitOptions}
        color={getColor('d')}
        dispatch={dispatch}
        onKeyDown={handleInputChange}
    />;

    React.useEffect(() => {
        if (inputARef.current) {
            // Focus on input A on page load.
            inputARef.current.focus();
        }
    }, []);

    return <div>
        <Header as='h1'>Ratio</Header>
        <Header as='h2'>A : B = C : D</Header>

        {baseDropdown}

        <Media at='mobile'>
            {inputA}
            {inputB}

            <hr/>

            {inputC}
            {inputD}
        </Media>

        <Media greaterThanOrEqual='tablet'>
            <Table className='ratio-table'>
                <Table.Body>
                    <Table.Row>
                        <Table.Cell className='equal-width'>{inputA}</Table.Cell>
                        <Table.Cell className='min-width'/>
                        <Table.Cell className='equal-width'>{inputC}</Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell className='equal-width'>
                            <hr/>
                        </Table.Cell>
                        <Table.Cell style={{textAlign: 'center'}} className='min-width'>
                            <Header as='h1'>=</Header>
                        </Table.Cell>
                        <Table.Cell className='equal-width'>
                            <hr/>
                        </Table.Cell>
                    </Table.Row>
                    <Table.Row>
                        <Table.Cell className='equal-width'>{inputB}</Table.Cell>
                        <Table.Cell className='min-width'/>
                        <Table.Cell className='equal-width'>{inputD}</Table.Cell>
                    </Table.Row>
                </Table.Body>
            </Table>
        </Media>
        <HandPointMessage storageName='hint_ratio_calculator'>
            <strong>Tip</strong> You can change inputs using the <b>a</b>, <b>b</b>, <b>c</b>, and <b>d</b> keys.
        </HandPointMessage>
    </div>
}

export const RatioCalculators = () => {
    return <RatioCalculator/>
}

// Exported for testing
export { ratioReducer };
