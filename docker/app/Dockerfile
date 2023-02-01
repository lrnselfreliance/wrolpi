# base image
FROM node:18-bullseye

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app/public /app/public
COPY app/src /app/src
COPY app/package.json app/package-lock.json /app/
RUN npm install
RUN npm install -g serve
RUN chown -R node:node /app

# Run the production build
CMD ["serve", "-s", "build"]
