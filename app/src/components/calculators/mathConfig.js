import {all, create} from "mathjs";

// Create a scoped math instance so custom units don't affect the global mathjs (used by RatioCalculator).
const math = create(all);

// Register custom radiation units.
// "rad" is already a built-in radian unit, so we use distinct alphanumeric names.
math.createUnit('gray', {aliases: ['Gy'], prefixes: 'short'});
math.createUnit('raddose', '0.01 gray');
math.createUnit('sievert', {aliases: ['Sv'], prefixes: 'short'});
math.createUnit('remdose', '0.01 sievert');
math.createUnit('roentgen', '0.00877 gray');
math.createUnit('becquerel', {definition: '1/s', aliases: ['Bq'], prefixes: 'short'});
math.createUnit('curie', '3.7e10 becquerel', {aliases: ['Ci']});

// Map internal unit names to user-friendly display names.
const UNIT_DISPLAY_NAMES = {
    'raddose': 'rad',
    'remdose': 'rem',
};

// Conversion groups: when a user enters a bare unit value, show these related conversions.
const CONVERSION_GROUPS = [
    {units: ['meter', 'km', 'mile', 'foot', 'inch', 'yard']},
    {units: ['kg', 'lbm', 'oz', 'g', 'grain', 'tonne']},
    {units: ['liter', 'gallon', 'quart', 'cup', 'fluidounce', 'ml', 'tablespoon', 'teaspoon']},
    {units: ['degF', 'degC', 'K']},
    {units: ['m/s', 'km/h', 'mi/h']},
    {units: ['Pa', 'psi', 'atm', 'bar', 'mmHg']},
    {units: ['J', 'kJ', 'Wh', 'kWh', 'BTU']},
    {units: ['W', 'kW', 'hp']},
    {units: ['b', 'Kb', 'Mb', 'Gb', 'Tb']},
    {units: ['gray', 'raddose', 'roentgen']},
    {units: ['sievert', 'remdose']},
    {units: ['becquerel', 'curie']},
    {units: ['N', 'lbf', 'kip']},
];

function formatUnit(unitValue) {
    let str = math.format(unitValue, {notation: 'fixed', precision: 4});
    // Strip trailing zeros after decimal point.
    str = str.replace(/(\.\d*?)0+(\s)/, '$1$2').replace(/\.(\s)/, '$1');
    // Replace internal unit names with friendly display names.
    for (const [internal, display] of Object.entries(UNIT_DISPLAY_NAMES)) {
        str = str.replace(new RegExp(`\\b${internal}\\b`, 'g'), display);
    }
    return str;
}

function findConversionGroup(result) {
    for (const group of CONVERSION_GROUPS) {
        for (const u of group.units) {
            try {
                result.to(u);
                return group;
            } catch {
                // Not compatible with this unit.
            }
        }
    }
    return null;
}

export function classifyAndEvaluate(inputStr) {
    const result = math.evaluate(inputStr);

    if (math.typeOf(result) !== 'Unit') {
        return {primary: result.toString(), conversions: []};
    }

    // If user explicitly used "to" or "in" for conversion, just return the single result.
    if (/\bto\b/i.test(inputStr) || /\bin\b/i.test(inputStr)) {
        return {primary: formatUnit(result), conversions: []};
    }

    const primaryStr = formatUnit(result);
    const conversions = [];
    const group = findConversionGroup(result);

    if (group) {
        for (const targetUnit of group.units) {
            try {
                const converted = result.to(targetUnit);
                const formatted = formatUnit(converted);
                if (formatted !== primaryStr) {
                    conversions.push(formatted);
                }
            } catch {
                // Skip incompatible (e.g. compound unit mismatch).
            }
        }
    }

    return {primary: primaryStr, conversions};
}
