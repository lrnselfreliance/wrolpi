const { defineConfig } = require("cypress");

module.exports = defineConfig({
  e2e: {
    // Use HTTP for CI, HTTPS for local development
    baseUrl: process.env.CI ? 'http://localhost:3000' : 'https://localhost:8443',
    specPattern: 'cypress/e2e/**/*.cy.js',
    supportFile: 'cypress/support/e2e.js',
    video: process.env.CI ? true : false,
    screenshotOnRunFailure: true,
  },
  component: {
    devServer: {
      framework: "create-react-app",
      bundler: "webpack",
    },
  },
});
