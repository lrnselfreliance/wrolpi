# base image
FROM node:13-buster

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app/public /app/public
COPY app/src /app/src
COPY app/package.json /app/
RUN rm -rf /app/node_modules /app/package-lock.json
RUN npm install
RUN npm install -g serve

# Run the production build
CMD ["serve", "-s", "build"]
