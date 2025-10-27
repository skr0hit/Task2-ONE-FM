# ------------------------------------------- Modified by SK Rohit ----------------------------------------------------------#

#                         This is the Customized Dockerfile for ONE-FM Frappe Application.

# ---------------------------------------------------------------------------------------------------------------------------#
ARG PYTHON_VERSION=3.11.6
ARG DEBIAN_BASE=bookworm
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_BASE} AS base

# --- MODIFIED --- Used complete path to avoid confusion
COPY frappe_docker/resources/nginx-template.conf /templates/nginx/frappe.conf.template
COPY frappe_docker/resources/nginx-entrypoint.sh /usr/local/bin/nginx-entrypoint.sh
# --- END MODIFIED ---

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ARG WKHTMLTOPDF_DISTRO=bookworm
ARG NODE_VERSION=20.19.2 # Changed to match Frappe v15+ requirements
ENV NVM_DIR=/home/frappe/.nvm
# Set PATH early, including potential node path
ENV PATH=${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN useradd -ms /bin/bash frappe \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
    curl \
    git \
    vim \
    nginx \
    gettext-base \
    file \
    # weasyprint dependencies
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    # For backups
    restic \
    gpg \
    # MariaDB
    mariadb-client \
    less \
    # Postgres
    libpq-dev \
    postgresql-client \
    # For healthcheck
    wait-for-it \
    jq \
    # For MIME type detection
    media-types \
    # NodeJS setup using NVM
    && mkdir -p ${NVM_DIR} \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash \
    && . ${NVM_DIR}/nvm.sh \
    && nvm install ${NODE_VERSION} \
    && nvm use v${NODE_VERSION} \
    && npm install -g yarn \
    && nvm alias default v${NODE_VERSION} \
    && rm -rf ${NVM_DIR}/.cache \
    && echo 'export NVM_DIR="/home/frappe/.nvm"' >>/home/frappe/.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm' >>/home/frappe/.bashrc \
    && echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion' >>/home/frappe/.bashrc \
    # Install wkhtmltopdf with patched qt
    && if [ "$(uname -m)" = "aarch64" ]; then export ARCH=arm64; fi \
    && if [ "$(uname -m)" = "x86_64" ]; then export ARCH=amd64; fi \
    && downloaded_file=wkhtmltox_${WKHTMLTOPDF_VERSION}.${WKHTMLTOPDF_DISTRO}_${ARCH}.deb \
    && curl -sLO https://github.com/wkhtmltopdf/packaging/releases/download/$WKHTMLTOPDF_VERSION/$downloaded_file \
    && apt-get install -y --allow-downgrades ./$downloaded_file \
    && rm $downloaded_file \
    # Clean up APT cache
    && rm -rf /var/lib/apt/lists/* \
    # Remove default Nginx site
    && rm -fr /etc/nginx/sites-enabled/default \
    # Fixes for non-root nginx and logs to stdout
    && sed -i '/user www-data/d' /etc/nginx/nginx.conf \
    && ln -sf /dev/stdout /var/log/nginx/access.log && ln -sf /dev/stderr /var/log/nginx/error.log
# <<<< END OF THE LONG RUN BLOCK

# --- Nginx Permissions ---
USER root 
RUN touch /run/nginx.pid \
    && chown -R frappe:frappe /etc/nginx/conf.d \
    && chown -R frappe:frappe /etc/nginx/nginx.conf \
    && chown -R frappe:frappe /var/log/nginx \
    && chown -R frappe:frappe /var/lib/nginx \
    && chown -R frappe:frappe /run/nginx.pid \
    && chown frappe:frappe /usr/local/bin/nginx-entrypoint.sh \
    && chmod 755 /usr/local/bin/nginx-entrypoint.sh \
    && chmod 644 /templates/nginx/frappe.conf.template

# --- Builder Stage ---
FROM base AS builder

# Install build dependencies
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    # For frappe framework
    wget \
    #for building arm64 binaries
    libcairo2-dev \
    libpango1.0-dev \
    libjpeg-dev \
    libgif-dev \
    librsvg2-dev \
    # For psycopg2 (Postgres client)
    libpq-dev \
    # Other potential build dependencies
    libffi-dev \
    liblcms2-dev \
    libldap2-dev \
    libmariadb-dev \
    libsasl2-dev \
    libtiff5-dev \
    libwebp-dev \
    pkg-config \
    redis-tools \
    rlwrap \
    tcl-dev \
    tk8.6-dev \
    cron \
    # For pandas (common dependency)
    gcc \
    build-essential \
    libbz2-dev \
    # Clean up APT cache
    && rm -rf /var/lib/apt/lists/*

# apps.json includes (still needed for bench init structure, even if empty)
ARG APPS_JSON_BASE64
RUN if [ -n "${APPS_JSON_BASE64}" ]; then \
    mkdir /opt/frappe && echo "${APPS_JSON_BASE64}" | base64 -d > /opt/frappe/apps.json; \
  fi

USER frappe

# --- Set PATH for frappe user's local bin ---
ENV PATH=/home/frappe/.local/bin:${PATH}

# --- Install bench *as the frappe user* ---
RUN pip3 install frappe-bench --break-system-packages

ARG FRAPPE_BRANCH=version-15
ARG FRAPPE_PATH=https://github.com/frappe/frappe
# Initialize bench ONLY with base Frappe app
RUN export APP_INSTALL_ARGS="" && \
    # apps.json is empty, so this arg won't install custom apps here
    if [ -n "${APPS_JSON_BASE64}" ]; then \
      export APP_INSTALL_ARGS="--apps_path=/opt/frappe/apps.json"; \
    fi && \
    # Now 'bench' will be found in the user's PATH
    bench init ${APP_INSTALL_ARGS}\
      --frappe-branch=${FRAPPE_BRANCH} \
      --frappe-path=${FRAPPE_PATH} \
      --no-procfile \
      --no-backups \
      --skip-redis-config-generation \
      --verbose \
      /home/frappe/frappe-bench && \
    cd /home/frappe/frappe-bench && \
    echo "{}" > sites/common_site_config.json

# --- COPY OUR CUSTOM APP CODE ---
COPY --chown=frappe:frappe custom_apps/one_fm_google_integration /home/frappe/frappe-bench/apps/one_fm_google_integration
# --- END OF COPY---

# --- NEW STEP: Install the custom app's Python package ---
RUN cd /home/frappe/frappe-bench && \
    ./env/bin/pip install --break-system-packages -e ./apps/one_fm_google_integration


# Clean up any .git directories that might have been copied
RUN cd /home/frappe/frappe-bench && \
    find apps -mindepth 1 -path "*/.git" | xargs rm -fr

# --- Final Backend Stage ---
FROM base AS backend

# --- FIX: Set PATH for frappe user's local bin ---
ENV PATH=/home/frappe/.local/bin:${PATH}

USER frappe

# Copy the entire initialized bench (including the manually added app) from the builder stage
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench

# --- FIX: Copy the user's local bin (which contains the 'bench' executable)
COPY --from=builder --chown=frappe:frappe /home/frappe/.local /home/frappe/.local

WORKDIR /home/frappe/frappe-bench

# Define volumes for persistent data
VOLUME [ \
  "/home/frappe/frappe-bench/sites", \
  "/home/frappe/frappe-bench/sites/assets", \
  "/home/frappe/frappe-bench/logs" \
]

# Default command to run the Frappe backend server
CMD [ \
  "/home/frappe/frappe-bench/env/bin/gunicorn", \
  "--chdir=/home/frappe/frappe-bench/sites", \
  "--bind=0.0.0.0:8000", \
  "--threads=4", \
  "--workers=2", \
  "--worker-class=gthread", \
  "--worker-tmp-dir=/dev/shm", \
  "--timeout=120", \
  "--preload", \
  "frappe.app:application" \
]
