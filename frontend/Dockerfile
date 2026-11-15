# SkyFleet frontend image: builds the Vite app and serves the production build with Vite Preview.
FROM node:24-slim

WORKDIR /app

# Dependencies first (cached layer), exactly as locked in package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Public build-time values only: everything prefixed VITE_ is bundled into the browser.
# The browser runs on the host, so it reaches the API through the host-published port.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_MAPBOX_TOKEN=
RUN npm run build

EXPOSE 5173
CMD ["node_modules/.bin/vite", "preview", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
