'use strict';

// Replaces CRA's JS transform so Jest can load three.js.  three (and three-stdlib) ship ES modules
// with static class blocks, which babel-preset-react-app's class-properties plugin rejects at our
// pinned Babel version.  Those files only need their imports converted to CommonJS; every other
// file goes through CRA's transform unchanged.
const babelJest = require('babel-jest').default;
const craTransform = require('react-scripts/config/jest/babelTransform');

const threeTransform = babelJest.createTransformer({
    babelrc: false,
    configFile: false,
    plugins: [require.resolve('@babel/plugin-transform-modules-commonjs')],
});

const THREE_PATH = /[\\/]node_modules[\\/]three(-stdlib)?[\\/]/;

function pick(sourcePath) {
    return THREE_PATH.test(sourcePath) ? threeTransform : craTransform;
}

module.exports = {
    canInstrument: true,
    getCacheKey(sourceText, sourcePath, options) {
        return pick(sourcePath).getCacheKey(sourceText, sourcePath, options);
    },
    process(sourceText, sourcePath, options) {
        return pick(sourcePath).process(sourceText, sourcePath, options);
    },
};
