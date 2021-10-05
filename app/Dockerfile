# base image
FROM node:13-buster

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app .env* /app/
RUN rm -rf /app/node_modules
RUN npm install --silent
RUN yarn

# Create the production build
RUN yarn run build
RUN yarn global add serve

# Run the production build
CMD ["serve", "-s", "build"]
