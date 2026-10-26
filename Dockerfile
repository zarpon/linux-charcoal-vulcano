FROM archlinux:base-devel

RUN mkdir /docker
ADD docker /docker/
RUN docker/setup.sh
RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -Eeuo pipefail' \
    'if [[ -d /project ]]; then' \
    '  chown nobody /project 2>/dev/null || true' \
    '  chown -R nobody /project/logs /project/.cache 2>/dev/null || true' \
    'fi' \
    'exec "$@"' \
    > /usr/local/bin/charcoal-entrypoint \
 && chmod 0755 /usr/local/bin/charcoal-entrypoint
WORKDIR /project
ENTRYPOINT ["/usr/local/bin/charcoal-entrypoint"]
