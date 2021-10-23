# base image
FROM node:13-buster

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app/public /app/public
COPY app/src /app/src
COPY app/package.json /app/
RUN rm -rf /app/node_modules
RUN npm install --silent
# Increase network timeout because a Raspberry Pi is slow.
RUN yarn --silent --network-timeout 100000

# Create the production build
RUN yarn run build
RUN yarn global add serve

# Run the production build
CMD ["serve", "-s", "build"]
