import {Container, Dropdown} from "semantic-ui-react";
import {Form, Header} from "../Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import {ThemeContext} from "../../contexts/contexts";
import React from "react";
import {roundDigits} from "../Common";
import {createUnit, multiply, unit} from "mathjs";

const nullUnit = createUnit('null');

function ratioReducer(prevState, e) {
    const {value, name} = Object.keys(e).indexOf('target') >= 0 ? e.target : e;
    let {a, aUnit, b, bUnit, c, cUnit, d, dUnit, base, lastUpdated} = prevState;
    console.log('ratioReducer', name, value, lastUpdated);

    a = unit(a, aUnit);
    b = unit(b, bUnit);
    c = unit(c, cUnit);
    d = unit(d, dUnit);

    // Keep a stack of which inputs are updated.  Limit it to the 3 most recent inputs.
    let newLastUpdated = lastUpdated || [];
    if (['a', 'b', 'c', 'd'].includes(name)) {
        newLastUpdated = newLastUpdated.filter(i => i !== name);
        newLastUpdated = [name, ...newLastUpdated];
        newLastUpdated = newLastUpdated.slice(0, 3);
    }

    console.log('a', a.toString(), 'b', b.toString(), 'c', c.toString(), 'd', d.toString());

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
        a = unit(value, aUnit);
    } else if (name === 'b') {
        b = unit(value, bUnit);
    } else if (name === 'c') {
        c = unit(value, cUnit);
    } else if (name === 'd') {
        d = unit(value, dUnit);
    } else if (name === 'base') {
        // Base is changing, reset units and values.
        base = value;
        aUnit = bUnit = cUnit = dUnit = baseToUnitsMap[base][0]['key'];
        a = b = c = d = unit(1, aUnit);
        // Reset last updated.
        newLastUpdated = [];
    }

    // Calculate ratio of the input which hasn't been updated recently.  But only if all other inputs have values.
    if (lastUpdated.length === 3) {
        if (!lastUpdated.includes('a')) {
            calculateA();
        } else if (!lastUpdated.includes('b')) {
            calculateB();
        } else if (!lastUpdated.includes('c')) {
            calculateC();
        } else if (!lastUpdated.includes('d')) {
            calculateD();
        }
    }

    return {
        base,
        lastUpdated: newLastUpdated,
        a: roundDigits(a.toNumber(), 3),
        b: roundDigits(b.toNumber(), 3),
        c: roundDigits(c.toNumber(), 3),
        d: roundDigits(d.toNumber(), 3),
        aUnit,
        bUnit,
        cUnit,
        dUnit,
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
        {key: 'cuin', value: 'cuin', text: 'cuin'},
        {key: 'cup', value: 'cup', text: 'cup'},
        {key: 'fluidounce', value: 'fluidounce', text: 'fluidounce'},
        {key: 'gallon', value: 'gallon', text: 'gallon'},
        {key: 'liter', value: 'liter', text: 'liter'},
        {key: 'm3', value: 'm3', text: 'meters³'},
        {key: 'milliliter', value: 'milliliter', text: 'ml'},
        {key: 'tablespoon', value: 'tablespoon', text: 'tablespoon'},
        {key: 'teaspoon', value: 'teaspoon', text: 'teaspoon'},
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
    ],
    'power': [
        {key: 'watt', value: 'watt', text: 'watt'},
        {key: 'hp', value: 'hp', text: 'hp'},
    ],
}

const initialState = {
    base: null,
    lastUpdated: [],
    a: '',
    b: '',
    c: '',
    d: '',
    aUnit: nullUnit,
    bUnit: nullUnit,
    cUnit: nullUnit,
    dUnit: nullUnit,
};

const RatioCalculator = () => {
    const {t} = React.useContext(ThemeContext);

    const [state, dispatch] = React.useReducer(ratioReducer, initialState);

    const unitOptions = baseToUnitsMap[state.base];

    const baseOptions = [
        {key: null, value: null, text: 'None'},
        {key: 'length', value: 'length', text: 'meter, feet, inch, etc.', label: 'Length'},
        {key: 'area', value: 'area', text: 'inch², m², etc.', label: 'Area'},
        {key: 'volume', value: 'volume', text: 'liter, m³, cup, etc.', label: 'Volume'},
        {key: 'mass', value: 'mass', text: 'gram, pound, etc.', label: 'Mass'},
        {key: 'energy', value: 'energy', text: 'joule, Wh, BTU', label: 'Energy'},
        {key: 'power', value: 'power', text: 'watt, horse power', label: 'Power'},
    ];

    const unitDropdownOptions = {
        options: unitOptions,
        className: 'label',
        onChange: (e, data) => dispatch(data),
    };

    const aColor = state.lastUpdated.indexOf('a') >= 0 ? '' : 'grey';
    const bColor = state.lastUpdated.indexOf('b') >= 0 ? '' : 'grey';
    const cColor = state.lastUpdated.indexOf('c') >= 0 ? '' : 'grey';
    const dColor = state.lastUpdated.indexOf('d') >= 0 ? '' : 'grey';

    return <Form>
        <Header as='h1'>Ratio</Header>

        <Grid columns={3}>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <Dropdown selection
                              fluid
                              placeholder='base'
                              options={baseOptions}
                              value={state.unit}
                              name='base'
                              onChange={(e, data) => dispatch(data)}
                    />
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={1}>
                <Grid.Column>
                    <Header as='h2'>A : B = C : D</Header>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column width={8}>
                    <div className="ui fluid labeled input">
                        <div className={`ui label ${aColor}`}>A</div>
                        <input
                            id="a"
                            name="a"
                            type="number"
                            value={state.a}
                            onChange={e => dispatch(e)}
                            onFocus={e => e.target.select()}
                        />
                        {state.base &&
                            <Dropdown {...unitDropdownOptions} name='aUnit' value={state.aUnit}/>}
                    </div>
                </Grid.Column>
                <Grid.Column width={1}/>
                <Grid.Column width={7}>
                    <div className="ui fluid labeled input">
                        <div className={`ui label ${cColor}`}>C</div>
                        <input
                            id="c"
                            name="c"
                            type="number"
                            value={state.c}
                            onChange={e => dispatch(e)}
                            onFocus={e => e.target.select()}
                        />
                        {state.base &&
                            <Dropdown {...unitDropdownOptions} name='cUnit' value={state.cUnit}/>}
                    </div>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column width={8}>
                    <hr/>
                </Grid.Column>
                <Grid.Column textAlign='center' width={1}>
                    <Header as='h1'>=</Header>
                </Grid.Column>
                <Grid.Column width={7}>
                    <hr/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row>
                <Grid.Column width={8}>
                    <div className="ui fluid labeled input">
                        <div className={`ui label ${bColor}`}>B</div>
                        <input
                            id="b"
                            name="b"
                            type="number"
                            value={state.b}
                            onChange={e => dispatch(e)}
                            onFocus={e => e.target.select()}
                        />
                        {state.base &&
                            <Dropdown {...unitDropdownOptions} name='bUnit' value={state.bUnit}/>}
                    </div>
                </Grid.Column>
                <Grid.Column width={1}/>
                <Grid.Column width={7}>
                    <div className="ui fluid labeled input">
                        <div className={`ui label ${dColor}`}>D</div>
                        <input
                            id="d"
                            name="d"
                            type="number"
                            value={state.d}
                            onChange={e => dispatch(e)}
                            onFocus={e => e.target.select()}
                        />
                        {state.base &&
                            <Dropdown {...unitDropdownOptions} name='dUnit' value={state.dUnit}/>}
                    </div>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </Form>
}

export const RatioCalculators = () => {
    return <Container>
        <RatioCalculator/>
    </Container>
}