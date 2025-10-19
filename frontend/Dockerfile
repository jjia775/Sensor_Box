# syntax=docker/dockerfile:1

# Stage 1: build the Vite/React application
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first to take advantage of Docker layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source and build it
COPY . .
RUN npm run build

# Stage 2: serve the compiled assets with Nginx
FROM nginx:1.27-alpine AS runner

# Copy the compiled assets from the build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose the default HTTP port
EXPOSE 80

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
