#!/usr/bin/env sh
# Копия проекта одним файлом: git bundle со всей историей + проверка. Запуск из корня проекта: ./backup_project.sh /mnt/backup
set -eu
DEST="${1:?укажите папку второго носителя, например ./backup_project.sh /mnt/backup}"
mkdir -p "$DEST"; F="$DEST/project-$(date +%Y%m%d).bundle"
git bundle create "$F" --all && git bundle verify "$F" && echo "готово: $F. Третья копия: git push -u origin <ветка> в удалённый репозиторий."
