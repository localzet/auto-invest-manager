FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine

WORKDIR /app
COPY server.mjs ./server.mjs
COPY --from=build /app/dist ./dist
USER node
EXPOSE 3000
CMD ["node", "server.mjs"]
