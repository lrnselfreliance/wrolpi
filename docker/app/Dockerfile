# base image
FROM node:13-buster

WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH

# install and cache app dependencies
COPY app .env* /app/
RUN rm -rf /app/node_modules
RUN npm install --silent
RUN yarn

# Remove external URLs
RUN apt install -y sed
RUN sed -i "s/@import url('https:\/\/fonts.googleapis.com\/css?family=Lato:400,700,400italic,700italic&subset=latin');//g" \
 /app/node_modules/semantic-ui-css/*.css
RUN sed -i "s/@import url(https:\/\/fonts.googleapis.com\/css?family=Lato:400,700,400italic,700italic&subset=latin);//g" \
 /app/node_modules/semantic-ui-css/components/*.css

# Create the production build
RUN yarn run build
RUN yarn global add serve

# Remove external URLs
RUN apt install -y sed
RUN sed -i "s/@import url('https:\/\/fonts.googleapis.com\/css?family=Lato:400,700,400italic,700italic&subset=latin');//g" \
 /app/node_modules/semantic-ui-css/*.css
RUN sed -i "s/@import url(https:\/\/fonts.googleapis.com\/css?family=Lato:400,700,400italic,700italic&subset=latin);//g" \
 /app/node_modules/semantic-ui-css/components/*.css


# Run the production build
CMD ["serve", "-s", "build"]
