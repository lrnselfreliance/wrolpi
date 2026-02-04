#!/usr/bin/env node
/**
 * Generate colored favicon SVGs from the base icon.svg
 *
 * Usage: node scripts/generate-favicons.js
 *
 * This script reads the base icon.svg and generates a colored version
 * for each color in semanticUIColorMap (from src/components/Vars.js).
 * The favicons are saved to public/favicon-{colorname}.svg
 */

const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, '..', 'src', 'components');
const publicDir = path.join(__dirname, '..', 'public');
const varsPath = path.join(srcDir, 'Vars.js');
const iconPath = path.join(publicDir, 'icon.svg');

// Parse semanticUIColorMap from Vars.js (single source of truth)
function parseColorMapFromVars() {
    const varsContent = fs.readFileSync(varsPath, 'utf8');

    // Extract the semanticUIColorMap object using regex
    const match = varsContent.match(/export const semanticUIColorMap\s*=\s*\{([^}]+)\}/);
    if (!match) {
        throw new Error('Could not find semanticUIColorMap in Vars.js');
    }

    const colorMap = {};
    const colorEntries = match[1].matchAll(/(\w+):\s*['"]([^'"]+)['"]/g);

    for (const entry of colorEntries) {
        colorMap[entry[1]] = entry[2];
    }

    if (Object.keys(colorMap).length === 0) {
        throw new Error('No colors found in semanticUIColorMap');
    }

    return colorMap;
}

// Parse colors from Vars.js
const semanticUIColorMap = parseColorMapFromVars();
console.log(`Found ${Object.keys(semanticUIColorMap).length} colors in Vars.js\n`);

// Colors that conflict with white stroke - use black stroke instead
// Must match Nav.js conflictingColors
const conflictingColors = ['red', 'orange', 'yellow', 'olive', 'pink'];

// Read the base icon
const iconSvg = fs.readFileSync(iconPath, 'utf8');

console.log('Generating colored favicons from icon.svg...\n');

// Generate a favicon for each color
for (const [colorName, hexColor] of Object.entries(semanticUIColorMap)) {
    // Replace the dark fill color (#1b1c1d) with the nav color
    let coloredSvg = iconSvg.replace(/fill:#1b1c1d/g, `fill:${hexColor}`);

    // Use black stroke for conflicting colors (better contrast)
    const useBlackStroke = conflictingColors.includes(colorName);
    if (useBlackStroke) {
        coloredSvg = coloredSvg.replace(/stroke:#ffffff/g, 'stroke:#000000');
    }

    const outputPath = path.join(publicDir, `favicon-${colorName}.svg`);
    fs.writeFileSync(outputPath, coloredSvg);

    const strokeInfo = useBlackStroke ? ', black stroke' : '';
    console.log(`  Created favicon-${colorName}.svg (${hexColor}${strokeInfo})`);
}

console.log(`\nGenerated ${Object.keys(semanticUIColorMap).length} favicon files in public/`);
