# ML Forge sandbox image: stdlib-only Python, non-root, harness baked in.
# Built by `make runner-build`; the tag is the sha of the harness files so the
# API can detect a stale image. Learner code never reaches this build.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

ARG HARNESS_SHA=unknown
LABEL org.opencontainers.image.title="mlforge-runner" \
      mlforge.harness_sha="${HARNESS_SHA}"

# No package managers at runtime; dedicated unprivileged user.
RUN python -m pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true \
 && groupadd --gid 10001 sandbox \
 && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin sandbox

COPY harness.py child.py /opt/mlforge/
RUN chmod 0555 /opt/mlforge && chmod 0444 /opt/mlforge/*.py

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONHASHSEED=0
USER 10001:10001
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "-X", "utf8", "/opt/mlforge/harness.py"]
