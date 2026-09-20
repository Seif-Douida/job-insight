# Airflow with this project's dependencies already installed.
#
# The development stack installs them at container start with
# `_PIP_ADDITIONAL_REQUIREMENTS`, which is fine on a laptop and wrong on a server: it turns
# every restart into a download, and a restart happens when the machine reboots, which is
# exactly when the network is least worth depending on.
#
# The image supplies dependencies; the repository is mounted at /opt/airflow/repo and
# PYTHONPATH points there, so the running code is whatever `git pull` last wrote. Updating
# the pipeline is a pull and a restart, and only a change to pyproject.toml needs a rebuild.

FROM apache/airflow:3.3.1

# Copied in dependency order: the layer below is rebuilt only when pyproject.toml changes,
# not every time a DAG is edited.
COPY --chown=airflow:0 pyproject.toml README.md /opt/airflow/app/
COPY --chown=airflow:0 pipeline /opt/airflow/app/pipeline

RUN pip install --no-cache-dir /opt/airflow/app

# A sanity check at build time rather than a traceback at three in the morning: the
# transform DAG shells out to dbt, so the image is not usable without it.
RUN dbt --version
