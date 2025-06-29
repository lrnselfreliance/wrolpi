# Build stage
FROM node:18-alpine AS builder
WORKDIR /app
ENV PATH=/app/node_modules/.bin:$PATH

# Copy package files and install production dependencies
COPY app/package.json app/package-lock.json ./
RUN npm ci --omit=dev

# Copy source files and build
COPY app/public ./public
COPY app/src ./src
RUN npm run build

# Runtime stage
FROM nginx:alpine
WORKDIR /usr/share/nginx/html

# Copy static build from builder stage
COPY --from=builder /app/build ./

# Expose port
EXPOSE 80

# Run Nginx
CMD ["nginx", "-g", "daemon off;"]