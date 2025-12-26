import {Dropdown, MessageHeader, TableBody, TableCell, TableRow} from "semantic-ui-react";
import {Form, Header, Table} from "../Theme";
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
        {key: 'centimeter', value: 'centimeter', text: 'centimeter'},
        {key: 'feet', value: 'feet', text: 'feet'},
        {key: 'inch', value: 'inch', text: 'inch'},
        {key: 'kilometer', value: 'kilometer', text: 'kilometer'},
        {key: 'meter', value: 'meter', text: 'meter'},
        {key: 'mile', value: 'mile', text: 'mile'},
    ],
    'area': [
        {key: 'm2', value: 'm2', text: 'm²'},
        {key: 'sqin', value: 'sqin', text: 'square inch'},
        {key: 'sqyd', value: 'sqyd', text: 'square yard'},
        {key: 'sqmi', value: 'sqmi', text: 'square mile'},
        {key: 'acre', value: 'acre', text: 'acre'},
        {key: 'hectare', value: 'hectare', text: 'hectare'},
    ],
    'volume': [
        {key: 'cc', value: 'cc', text: 'cc'},
        {key: 'liter', value: 'liter', text: 'liter'},
        {key: 'm3', value: 'm3', text: 'meters³'},
        {key: 'cup', value: 'cup', text: 'cup'},
        {key: 'fluidounce', value: 'fluidounce', text: 'fl.oz'},
        {key: 'gallon', value: 'gallon', text: 'gallon'},
        {key: 'quart', value: 'quart', text: 'quart'},
        {key: 'milliliter', value: 'milliliter', text: 'ml'},
        {key: 'tablespoon', value: 'tablespoon', text: 'tablespoon'},
        {key: 'teaspoon', value: 'teaspoon', text: 'teaspoon'},
        {key: 'cuin', value: 'cuin', text: 'cuin'},
    ],
    'mass': [
        {key: 'grain', value: 'grain', text: 'grain'},
        {key: 'gram', value: 'gram', text: 'gram'},
        {key: 'lbs', value: 'lbs', text: 'pound'},
        {key: 'stone', value: 'stone', text: 'stone'},
        {key: 'ton', value: 'ton', text: 'ton'},
    ],
    'energy': [
        {key: 'joule', value: 'joule', text: 'joule'},
        {key: 'Wh', value: 'Wh', text: 'Wh'},
        {key: 'BTU', value: 'BTU', text: 'BTU'},
        {key: 'watt', value: 'watt', text: 'watt'},
        {key: 'hp', value: 'hp', text: 'hp'},
    ],
};

// Used to get from unit like `BTU` back to the base `energy`.
let unitsToBaseMap = {};
for (const [base, units] of Object.entries(baseToUnitsMap)) {
    for (const {key} of units) {
        unitsToBaseMap[key] = base;
    }
}

const defaultUnits = {
    // These will be replaced using local storage.
    length: baseToUnitsMap.length[0]['key'], // centimeter
    area: baseToUnitsMap.area[0]['key'], // m2
    volume: baseToUnitsMap.volume[0]['key'], // cc
    mass: baseToUnitsMap.mass[0]['key'], // grain
    energy: baseToUnitsMap.energy[0]['key'], // joule
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

const baseOptions = [
    {key: null, value: null, text: 'None'},
    {key: 'length', value: 'length', label: 'meter, feet, inch, etc.', text: 'Length'},
    {key: 'area', value: 'area', label: 'inch², m², etc.', text: 'Area'},
    {key: 'volume', value: 'volume', label: 'liter, m³, cup, etc.', text: 'Volume'},
    {key: 'mass', value: 'mass', label: 'gram, pound, etc.', text: 'Mass'},
    {key: 'energy', value: 'energy', label: 'joule, watt, etc.', text: 'Energy'},
];

const RatioInput = React.forwardRef(({name, label, value, unitValue, unitName, unitOptions, color, dispatch, onKeyDown}, ref) => (
    <div className="ui fluid labeled input" style={{marginBottom: '0.25em'}}>
        <div className={`ui label ${color}`}>{label}</div>
        <input
            id={name}
            name={name}
            type="number"
            ref={ref}
            value={unitToInputValue(value)}
            onChange={e => dispatch(e)}
            onKeyDown={onKeyDown}
            onFocus={e => e.target.select()}
        />
        {unitOptions &&
            <Dropdown
                options={unitOptions}
                className='label'
                onChange={(_, data) => dispatch(data)}
                name={unitName}
                value={unitValue}
            />}
    </div>
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

    const getColor = (name) => state.lastUpdated.includes(name) ? '' : 'grey';

    const baseDropdown = <Dropdown selection
                                   fluid
                                   placeholder='Base Units'
                                   options={baseOptions}
                                   value={state.base}
                                   name='base'
                                   onChange={(_, data) => dispatch(data)}
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

    return <Form>
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
            <Table unstackable className='ratio-table'>
                <TableBody>
                    <TableRow>
                        <TableCell className='equal-width'>{inputA}</TableCell>
                        <TableCell className='min-width'/>
                        <TableCell className='equal-width'>{inputC}</TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell className='equal-width'>
                            <hr/>
                        </TableCell>
                        <TableCell textAlign='center' className='min-width'>
                            <Header as='h1'>=</Header>
                        </TableCell>
                        <TableCell className='equal-width'>
                            <hr/>
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell className='equal-width'>{inputB}</TableCell>
                        <TableCell className='min-width'/>
                        <TableCell className='equal-width'>{inputD}</TableCell>
                    </TableRow>
                </TableBody>
            </Table>
        </Media>
        <HandPointMessage storageName='hint_ratio_calculator'>
            <MessageHeader>Tip</MessageHeader>
            You can change inputs using the <b>a</b>, <b>b</b>, <b>c</b>, and <b>d</b> keys.
        </HandPointMessage>
    </Form>
}

export const RatioCalculators = () => {
    return <RatioCalculator/>
}

// Exported for testing
export { ratioReducer };
