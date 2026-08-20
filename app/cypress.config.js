const path = require("path");
const fs = require("fs");
const { defineConfig } = require("cypress");

/*
 * Real-file tasks for the FileBrowser e2e tests.
 *
 * The tests exercise the live stack (delete/rename/move really happen), so every task is
 * jailed to one sandbox directory inside the media directory.  `test/` also holds shared
 * fixtures the whole suite depends on -- a task that could write or delete outside the
 * sandbox would let a buggy test destroy them.
 */
const MEDIA_DIR = process.env.WROLPI_MEDIA_DIR || path.resolve(__dirname, "..", "test");
const SANDBOX_NAME = "cypress-fb";
const SANDBOX_DIR = path.join(MEDIA_DIR, SANDBOX_NAME);

function sandboxPath(relativePath) {
  const resolved = path.resolve(SANDBOX_DIR, relativePath || ".");
  if (resolved !== SANDBOX_DIR && !resolved.startsWith(SANDBOX_DIR + path.sep)) {
    throw new Error(`Refusing to touch path outside the sandbox: ${relativePath}`);
  }
  return resolved;
}

const fileBrowserTasks = {
  // Wipe the sandbox (including leftovers from a crashed run) and create the given files.
  // `files` maps sandbox-relative paths to file content; a trailing '/' makes a bare directory.
  "fb:reset": ({ files }) => {
    fs.rmSync(SANDBOX_DIR, { recursive: true, force: true });
    fs.mkdirSync(SANDBOX_DIR, { recursive: true });
    for (const [relativePath, content] of Object.entries(files || {})) {
      if (relativePath.endsWith("/")) {
        fs.mkdirSync(sandboxPath(relativePath), { recursive: true });
      } else {
        const filePath = sandboxPath(relativePath);
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, content ?? "");
      }
    }
    return SANDBOX_NAME;
  },
  // Add files to the existing sandbox without wiping it (e.g. behind the UI's back).
  "fb:seed": ({ files }) => {
    for (const [relativePath, content] of Object.entries(files || {})) {
      const filePath = sandboxPath(relativePath);
      fs.mkdirSync(path.dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, content ?? "");
    }
    return true;
  },
  "fb:exists": (relativePath) => fs.existsSync(sandboxPath(relativePath)),
  "fb:readdir": (relativePath) => {
    const dir = sandboxPath(relativePath);
    return fs.existsSync(dir) ? fs.readdirSync(dir).sort() : null;
  },
  "fb:cleanup": () => {
    fs.rmSync(SANDBOX_DIR, { recursive: true, force: true });
    return true;
  },
  // Tagging creates a hardlink under <media>/tags/<TagName>/, and a force-deleted file
  // leaves that link behind (the tags-directory sync refuses to remove it).  Only tag
  // directories created by these tests may be removed: the name must start with 'CypressFB'.
  "fb:cleanup-tag-dir": (tagName) => {
    if (!/^CypressFB[A-Za-z0-9]*$/.test(tagName)) {
      throw new Error(`Refusing to remove tag directory not owned by the tests: ${tagName}`);
    }
    fs.rmSync(path.join(MEDIA_DIR, "tags", tagName), { recursive: true, force: true });
    return true;
  },
};

module.exports = defineConfig({
  e2e: {
    setupNodeEvents(on) {
      on("task", fileBrowserTasks);
    },
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
