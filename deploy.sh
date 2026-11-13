#!/usr/bin/env bash
# Обновление бота на сервере: подтянуть код из git и пересобрать контейнер.
# Использование:  ./deploy.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "Нет файла .env — скопируйте .env.example и заполните токены." >&2
    exit 1
fi

echo ">>> текущая версия: $(git rev-parse --short HEAD)"
git pull --ff-only
echo ">>> новая версия:   $(git rev-parse --short HEAD)"

docker compose up -d --build
docker image prune -f >/dev/null 2>&1 || true

echo ">>> статус"
docker compose ps --format "table {{.Name}}\t{{.Status}}"
echo ">>> последние строки лога"
docker compose logs --no-color --tail 5
