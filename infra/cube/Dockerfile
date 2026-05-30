# Cube container for Insights Navigator V2.0 (Phase 5b).
#
# Pinned to a specific Cube version for reproducibility. Verify the tag is
# still current before deploy: https://hub.docker.com/r/cubejs/cube/tags
FROM cubejs/cube:v1.6.52

WORKDIR /cube/conf

# Install the one extra dep our config needs (GCS reads for the model layer).
COPY package.json ./
RUN npm install --omit=dev

# Our config layer. The data model itself is fetched from GCS at runtime
# (see cube.js repositoryFactory), NOT copied here.
COPY cube.js ./

# Cube's API server binds to $PORT (Cloud Run injects 8080). The base image's
# entrypoint already starts the server, so no CMD override needed.
EXPOSE 4000
