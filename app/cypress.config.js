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
      /*
       * Cypress 14 removed the built-in create-react-app dev server, so the webpack config
       * this project builds with has to be handed over explicitly.  Until it was, every
       * component run ended in `Unexpected framework create-react-app`.
       *
       * The config comes from react-scripts rather than being written out here, so the
       * components under test are compiled exactly as `npm start` compiles them -- same
       * babel, same loaders, same resolve rules.  Cypress supplies the entry, the output
       * and the HTML shell, so those are dropped along with the plugins that would fight
       * it for them.
       */
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

        /*
         * react-scripts compiles `src` and nothing else, so the support file -- which is
         * JSX, and lives in `cypress/` -- reached babel-loader with no preset and failed on
         * its first tag.  The support file and the specs are as much "our code" as `src` is.
         */
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
