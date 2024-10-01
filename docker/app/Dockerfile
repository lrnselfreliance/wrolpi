# base image
FROM node:18-bullseye

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
USER root
RUN npm install -g serve
COPY app/public /app/public
COPY app/src /app/src
COPY app/package.json app/package-lock.json /app/
# "node" user will run the app after build.
RUN chown -R node:node /app

# Install dependencies as "node", this is to avoid changing ownership of many files.
USER node
RUN npm install

# Run the production build
CMD ["npm", "run", "start"]
