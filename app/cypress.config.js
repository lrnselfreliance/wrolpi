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

function fileContent(content) {
  return content && content.base64 !== undefined ? Buffer.from(content.base64, "base64") : (content ?? "");
}

const fileBrowserTasks = {
  // Wipe the sandbox (including leftovers from a crashed run) and create the given files.
  // `files` maps sandbox-relative paths to file content; a trailing '/' makes a bare directory.
  // Content is text, or `{base64: '...'}` for a binary file.
  "fb:reset": ({ files }) => {
    fs.rmSync(SANDBOX_DIR, { recursive: true, force: true });
    fs.mkdirSync(SANDBOX_DIR, { recursive: true });
    for (const [relativePath, content] of Object.entries(files || {})) {
      if (relativePath.endsWith("/")) {
        fs.mkdirSync(sandboxPath(relativePath), { recursive: true });
      } else {
        const filePath = sandboxPath(relativePath);
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, fileContent(content));
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

/*
 * Real map files for the standalone map viewer's e2e test, jailed to one directory inside the
 * media directory's map directory.
 */
const zlib = require("zlib");

const MAP_SANDBOX_NAME = "cypress-map";
const MAP_SANDBOX_DIR = path.join(MEDIA_DIR, "map", MAP_SANDBOX_NAME);

// A PMTiles version 3 file with a header, metadata and an empty tile directory: enough for the
// map to list and add it, with no tiles to draw.
function pmtilesFile(metadata) {
  const directory = zlib.gzipSync(Buffer.from([0]));
  const meta = zlib.gzipSync(Buffer.from(JSON.stringify(metadata)));
  const header = Buffer.alloc(127);
  header.write("PMTiles", 0, "latin1");
  header[7] = 3;
  header.writeBigUInt64LE(127n, 8);
  header.writeBigUInt64LE(BigInt(directory.length), 16);
  header.writeBigUInt64LE(BigInt(127 + directory.length), 24);
  header.writeBigUInt64LE(BigInt(meta.length), 32);
  // Clustered, internal compression gzip, tile compression gzip, tile type mvt, zoom 0-8.
  Buffer.from([1, 2, 2, 1, 0, 8]).copy(header, 96);
  header.writeInt32LE(-1800000000, 102);
  header.writeInt32LE(-850000000, 106);
  header.writeInt32LE(1800000000, 110);
  header.writeInt32LE(850000000, 114);
  return Buffer.concat([header, directory, meta]);
}

const mapTasks = {
  // Wipe the sandbox and create an overlay file there, with a style beside it if given.
  "map:seed-overlay": ({ name, metadata, style }) => {
    if (!/^[a-z-]+$/.test(name)) throw new Error(`Refusing the map file name: ${name}`);
    fs.rmSync(MAP_SANDBOX_DIR, { recursive: true, force: true });
    fs.mkdirSync(MAP_SANDBOX_DIR, { recursive: true });
    fs.writeFileSync(path.join(MAP_SANDBOX_DIR, `${name}.pmtiles`), pmtilesFile(metadata));
    if (style) fs.writeFileSync(path.join(MAP_SANDBOX_DIR, `${name}.style.json`), JSON.stringify(style));
    return `${MAP_SANDBOX_NAME}/${name}.pmtiles`;
  },
  "map:cleanup": () => {
    fs.rmSync(MAP_SANDBOX_DIR, { recursive: true, force: true });
    return true;
  },
};

module.exports = defineConfig({
  e2e: {
    setupNodeEvents(on) {
      on("task", fileBrowserTasks);
      on("task", mapTasks);
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
