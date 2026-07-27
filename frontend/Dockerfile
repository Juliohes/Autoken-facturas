# Frontend Autoken Facturas v2 — build estático servido por nginx (despliegue real, S5.x)
# Multi-stage: compila con Node, sirve solo los ficheros estáticos (nginx nunca ve node_modules).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
