# Project Knowledge — реализация и технические проверки, 2026-11-03

Добавлены project init/status/map/map-check. У нового проекта отдельная пустая SQLite в .harness/knowledge, meta связывает её с project_id. CLI выбирает базу по cwd до Git root или явному --project-root; --db/env могут явно перенаправить store. Legacy global база сохранена, миграция не выполнялась.

Knowledge Core уже поддерживал project observations/procedures, tags/symbols/evidence и revision updates. Skill дополнен правилами поддержания карты кода, фактов о сервисах и runbooks. Карта извлекает выбранные files/hashes/Python AST declarations, проверяет freshness и даёт краткие навигационные hints Scout. Она не доказывает service behavior и не меняет KB entries автоматически.

Временные alpha/beta проекты при init получили нулевые tasks/entries/evidence/jobs/packets. В каждом независимо создана задача same-task-id; из nested cwd wrapper выбрал соответствующую DB. Повторный init сохранил задачу. Неверные project_id и конфликтующий init отклонены. Явный project root снаружи работает. Клон с profile без DB по явному init получает пустую DB, без восстановления старых знаний.

Python fixture дал Client и Client.fetch; map-check current → stale после изменения; refresh обновил карту. Формат knowledge-cycle прошёл quick_validate, модули компилируются. [Операционные receipts](../../evals/knowledge-projects/2026-11-03/operational.json).

Это авторские технические проверки, не независимый тестовый suite. Новые тесты не генерировались, полная regression suite не запускалась. Общие general знания из другой DB не федератируются автоматически. Init не устанавливает skills/hooks и не переписывает project instructions; цикл нужно явно включить в новом проекте. OS isolation, full call graph, миграция старой базы и автоматическое обновление всех архитектурных claims не реализованы.
