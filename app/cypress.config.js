const path = require("path");
const { defineConfig } = require("cypress");

module.exports = defineConfig({
  e2e: {
    // Use HTTP for CI, HTTPS for local development
    baseUrl: process.env.CI ? 'http://localhost:3000' : 'https://localhost:8443',
    specPattern: 'cypress/e2e/**/*.cy.js',
    supportFile: 'cypress/support/e2e.js',
    video: process.env.CI ? true : false,
    screenshotOnRunFailure: true,
    env: {
      CI: !!process.env.CI,
    },
  },
  component: {
    devServer: {
      // Cypress removed its create-react-app framework, so hand it the same webpack config
      // `npm start` uses, minus the entry, output and HTML plugins Cypress supplies itself.
      framework: "react",
      bundler: "webpack",
      webpackConfig: () => {
        // react-scripts reads both of these at require time.
        process.env.NODE_ENV = process.env.NODE_ENV || 'development';
        process.env.BABEL_ENV = process.env.BABEL_ENV || 'development';
        const config = require('react-scripts/config/webpack.config')('development');
        delete config.entry;
        delete config.output;
        delete config.optimization;
        const cypressOwnsThese = [
          'HtmlWebpackPlugin', 'InterpolateHtmlPlugin', 'MiniCssExtractPlugin',
          'WebpackManifestPlugin', 'ManifestPlugin', 'ModuleNotFoundPlugin',
          'ForkTsCheckerWebpackPlugin',
        ];
        config.plugins = (config.plugins || [])
          .filter(plugin => !cypressOwnsThese.includes(plugin.constructor.name));

        // react-scripts only babel-loads `src`; the JSX support file lives in `cypress/`.
        const alsoCompile = [path.resolve(__dirname, 'cypress')];
        const widenBabel = (rules) => rules.forEach((rule) => {
          if (rule.oneOf) return widenBabel(rule.oneOf);
          const loader = String(rule.loader || '');
          if (loader.includes('babel-loader') && rule.include) {
            rule.include = [].concat(rule.include, alsoCompile);
          }
        });
        widenBabel(config.module.rules);

        return config;
      },
    },
  },
});
