# base image
FROM node:18-bullseye

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
USER root
RUN npm install -g serve
COPY app/public /app/public
COPY app/src /app/src
COPY app/package.json app/package-lock.json app/tsconfig.json app/serve.json /app/
# "node" user will run the app after build.
RUN chown -R node:node /app

# Install dependencies as "node", this is to avoid changing ownership of many files.
USER node
RUN npm install

# Build the production bundle (emits the PWA service worker; the dev server does not).
RUN npm run build

# Serve the production build, matching the native wrolpi-app.service.  serve.json keeps the SPA fallback while
# serving real files (service-worker.js, epub.html) directly.
CMD ["serve", "build", "-l", "3000", "-c", "/app/serve.json"]
