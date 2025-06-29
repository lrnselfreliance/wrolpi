FROM node:18-alpine
WORKDIR /app
ENV PATH=/app/node_modules/.bin:$PATH

# Install serve and production dependencies
RUN npm install -g serve && \
    npm cache clean --force

# Copy package files and install production dependencies
COPY app/package.json app/package-lock.json ./
RUN npm ci --omit=dev && \
    npm cache clean --force

# Copy source files and build
COPY app/public ./public
COPY app/src ./src
RUN npm run build

# Serve the production build
CMD ["serve", "-s", "build", "-l", "3000"]
