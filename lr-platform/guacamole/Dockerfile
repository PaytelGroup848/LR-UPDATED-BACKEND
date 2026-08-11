FROM maven:3-eclipse-temurin-8-focal AS builder

ARG GUACAMOLE_VERSION=1.6.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN git clone --depth 1 --branch "${GUACAMOLE_VERSION}" \
    https://github.com/apache/guacamole-client.git source

COPY guacamole/client-ui.patch /build/client-ui.patch

WORKDIR /build/source

# Apply LR's presentation-only changes to the original Guacamole frontend
# sources, then build the WAR using Guacamole's version-pinned frontend toolchain.
RUN git apply --check /build/client-ui.patch \
    && git apply /build/client-ui.patch \
    && mvn --batch-mode --no-transfer-progress \
        -pl guacamole -am package -DskipTests

FROM guacamole/guacamole:1.6.0

COPY --from=builder /build/source/guacamole/target/guacamole-1.6.0.war \
    /opt/guacamole/webapp/guacamole.war
