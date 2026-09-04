FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN apk add --no-cache libc6-compat
RUN npm install

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG API_URL=http://backend:8000/api
ENV API_URL=$API_URL
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
