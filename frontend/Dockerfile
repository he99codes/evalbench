FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# Dev server for local development (compose bind-mounts the source for hot reload).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
