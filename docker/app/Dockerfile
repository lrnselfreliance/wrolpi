# base image
FROM node:13-buster

# set working directory
WORKDIR /app

# add `/app/node_modules/.bin` to $PATH
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app .env* /app/
RUN npm install --silent
RUN npm install react-scripts@3.3.0 -g --silent

# Create the production build
RUN yarn run build
RUN yarn global add serve

# start app
CMD ["serve", "-s", "build"]
