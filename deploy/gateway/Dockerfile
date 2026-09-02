FROM node:22-alpine AS frontend-builder

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_API_BASE_URL=/django/api
ARG VITE_SPRING_API_BASE_URL=/spring/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_SPRING_API_BASE_URL=${VITE_SPRING_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/ || exit 1
