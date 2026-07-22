FROM node:22-alpine AS build

WORKDIR /frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG VITE_BACKEND_BASE_URL
ENV VITE_BACKEND_BASE_URL=${VITE_BACKEND_BASE_URL} \
    VITE_USE_MOCK_API=false
RUN npm run build:main

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /frontend/dist /usr/share/nginx/html
EXPOSE 8080
