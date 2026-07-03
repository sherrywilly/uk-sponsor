FROM node:20-alpine AS build

WORKDIR /app

COPY platform_dashboard/package*.json ./
RUN npm ci || npm install

COPY platform_dashboard/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY platform_dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
