# syntax=docker/dockerfile:1.7

FROM rocker/r-ver:4.5.3@sha256:c3f39b365d1077fe24f8e9ab2742e352b6d3950897f51af1624a5bb5550c21c0 AS builder

ARG HMISC_COMMIT=778bd69d83961577be1f73fa1e36781bd3fd099f
ARG RMS_DESCRIPTION_SHA256=0528cd8378601f0b05a6e6fb3daa89e8dfc6211adb82246c2f4eb7dec12ae23b

ENV DEBIAN_FRONTEND=noninteractive
ENV RSPM=https://p3m.dev/cran/__linux__/noble/2026-04-23

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        gfortran \
        git \
        libcurl4-openssl-dev \
        libfontconfig1-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libjpeg-dev \
        libpng-dev \
        libssl-dev \
        libtiff-dev \
        libxml2-dev \
        make \
    && rm -rf /var/lib/apt/lists/*

RUN install2.r --error --skipinstalled --ncpus -1 \
        Hmisc \
        SparseM \
        colorspace \
        digest \
        ggplot2 \
        htmlTable \
        htmltools \
        jsonlite \
        knitr \
        multcomp \
        polspline \
        quantreg \
        scales \
        tinytable

RUN git clone --filter=blob:none https://github.com/harrelfe/Hmisc.git /tmp/Hmisc \
    && git -C /tmp/Hmisc checkout --detach "${HMISC_COMMIT}" \
    && test "$(git -C /tmp/Hmisc rev-parse HEAD)" = "${HMISC_COMMIT}" \
    && R CMD INSTALL --clean --no-multiarch /tmp/Hmisc \
    && Rscript --vanilla -e \
        'stopifnot(utils::packageVersion("Hmisc") >= "5.3.0")'

COPY --from=rms_source . /tmp/rms-source
COPY reference/manifests/rms-8.2-0-files.sha256 /opt/holocron/rms-8.2-0-files.sha256

RUN cd /tmp/rms-source \
    && sha256sum --check --strict /opt/holocron/rms-8.2-0-files.sha256 \
    && echo "${RMS_DESCRIPTION_SHA256}  DESCRIPTION" | sha256sum --check --strict \
    && R CMD INSTALL --clean --no-multiarch /tmp/rms-source \
    && Rscript --vanilla -e \
        'stopifnot(as.character(packageVersion("rms")) == "8.2.0")'

FROM rocker/r-ver:4.5.3@sha256:c3f39b365d1077fe24f8e9ab2742e352b6d3950897f51af1624a5bb5550c21c0 AS oracle

LABEL org.opencontainers.image.title="Holocron rms parity oracle" \
      org.opencontainers.image.description="Test-only R rms oracle; not a Holocron runtime dependency" \
      org.holocron.r-version="4.5.3" \
      org.holocron.rms-version="8.2-0" \
      org.holocron.rms-commit="a4e4a305a029090e737562fb4d35bdb705db7d63" \
      org.holocron.rms-description-sha256="0528cd8378601f0b05a6e6fb3daa89e8dfc6211adb82246c2f4eb7dec12ae23b" \
      org.holocron.r-repository="https://p3m.dev/cran/__linux__/noble/2026-04-23" \
      org.holocron.hmisc-commit="778bd69d83961577be1f73fa1e36781bd3fd099f"

ENV DEBIAN_FRONTEND=noninteractive \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    RSPM=https://p3m.dev/cran/__linux__/noble/2026-04-23 \
    TZ=UTC

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        gfortran \
        libcurl4-openssl-dev \
        libfontconfig1-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libjpeg-dev \
        libpng-dev \
        libssl-dev \
        libtiff-dev \
        libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/R/site-library /usr/local/lib/R/site-library
COPY reference/r/oracle.R /opt/holocron/oracle.R

RUN groupadd --system --gid 10001 oracle \
    && useradd --system --uid 10001 --gid oracle --no-create-home oracle

USER 10001:10001
ENTRYPOINT ["Rscript", "--vanilla", "/opt/holocron/oracle.R"]
