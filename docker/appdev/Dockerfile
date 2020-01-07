# base image
FROM node:13-buster

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# Copy app and .env.  .env may not exist.
COPY app .env* /app/

# install dependencies
RUN npm install --silent
RUN npm install react-scripts@3.3.0 -g --silent

# Run the development build
CMD ["serve"]