# Выполнение skill v0.1

Это команды подготовки для координатора; генерирует тесты другой агент. Во всех примерах пути замени конкретными. SKILL — корень этого skill. Рабочие результаты храни в `.harness/testing/<task>-<run>` выбранного проекта либо в явно заданном каталоге. Не помещай private данные в этот каталог.

## 1. Подготовить контракт и plan

На основе `assets/spec.md` сформулируй открытый контракт с requirement IDs, интерфейсами, oracle, допустимыми входами и запуском. Не оставляй незаполненный шаблон. Укажи after, если реализация уже существует. Phase — честная декларация координатора, CLI не умеет установить историческую независимость.

```sh
python3 SKILL/scripts/testing.py init --task-id ttl --spec /path/spec.md --run .harness/testing/ttl-1 --suite public --suite private --suite adversarial --phase before
```

Без --suite выбирается только public. Повторный init не перезаписывает run. Spec копируется и связывается с plan digest. Изменив контракт, создай новый run; старые evidence сохраняются. Defaults берутся из defaults.json, overrides: `--budget-seconds`, `--budget-cases`, `--budget-findings`, `--private-queries`. Это верхние advisory лимиты, не требование истратить их; остановись раньше при достаточном результате. Для ML/GPU задай ресурсный контракт отдельно. Query budget относится к task, а не run; при будущей private интеграции счётчик должен вести evaluator, не эта утилита.

## 2. Передать public генератору

```sh
python3 SKILL/scripts/testing.py brief --run .harness/testing/ttl-1 --role public --output-scope /absolute/path/test-output
```

Передай `prompt` из JSON в новый native worker без полной истории разработчика. Путь к шаблону результата уже включён в brief. До передачи проверь, что spec содержит только нужные открытые данные, output_scope не пересекается с candidate/продуктом, а доступные команды авторизованы. CLI не проверяет смысл спецификации и не выдаёт права. Получи краткий итог и `worker-result.json`; тесты разработчик может читать и запускать. Готовые тесты переносить в проект можно в рамках явно указанного scope. Сохрани исходный пакет и digest; не смешивай initial suite с последующими regressions.

Private brief в этой версии вернёт `status:unavailable`, `reason:private_backend_unavailable`, exit 2. Не обходи это отдельной папкой или обычным subagent. Продолжай выбранные public/adversarial, но итог full остаётся partial. Для внешнего защищённого evaluator сначала нужна отдельная проверенная интеграция по private-evaluation.md.

## 3. Зафиксировать решение и атаковать

Создай environment.json с реально известными runtime/dependency lock IDs, OS/architecture и при необходимости data/model/hardware/seed. Пустой object технически допустим, но не доказывает воспроизводимость. Перечисли файлы scope явно, включая новые/dirty, lockfiles и конфигурацию; CLI не сканирует git автоматически и не включает весь репозиторий. Не включай secrets. Не редактируй source во время копирования: это последовательное чтение файлов, не атомарный filesystem snapshot.

```sh
python3 SKILL/scripts/testing.py freeze --run .harness/testing/ttl-1 --root /path/project --files src/cache.py pyproject.toml uv.lock --environment /path/environment.json
python3 SKILL/scripts/testing.py verify --candidate /absolute/path/candidates/DIGEST
python3 SKILL/scripts/testing.py brief --run .harness/testing/ttl-1 --role adversarial --candidate /absolute/path/candidates/DIGEST --output-scope /absolute/path/attack-output
```

Freeze возвращает `candidate` и `candidate_ref`. Digest зависит от spec, выбранных путей/байтов, executable flags и environment. Содержимое копируется в `tree`; symlinks, traversal и special files не допускаются. Verify проверяет manifest identity, содержимое и состав файлов tree. Это защита от случайного drift, не trusted sealing: владелец файлов может пересоздать manifest и ID.

Adversarial worker читает frozen tree, выполняет проверки на отдельной disposable копии и возвращает evidence для этого candidate. Не тестируй незаметно текущую рабочую копию. Verify до и после исполнения; при drift результат inconclusive до повторного запуска на правильном snapshot. Тестовый runner может создавать caches в disposable copy; исходный tree не изменяй.

## 4. Принять результаты

Прочитай разрешённый worker-result.json, а не transcript. Шаблон — форма передачи, не schema validator и не доказательство успеха. Проверь обязательные связи task/spec/candidate и пути артефактов. Проверь, что executed checks действительно имеют evidence и не указывают на другой candidate; при существенном сомнении воспроизведи конкретную готовую проверку. Не редактируй сами тесты в контексте разработчика: отправь корректировку тому же public/adversarial worker.

Допустимые статусы описаны в [инструкции генератору](worker.md#результат) и включаются в brief. no_counterexample_found не превращается в общий pass. Отчёт отдельно показывает выбранные public/private/adversarial, provenance и ограничения. Неиспользованные ветки — not_requested, а не пройденные проверки.

При готовом решении можно отдельно вызвать attack: init с `--phase after --suite adversarial`, freeze, brief. Если готовые тесты уже существуют, evaluate запускает их обычным runner, новые агенты для простого исполнения не нужны. Full — координация этих шагов нативным агентом, не отдельный daemon/автоматический state machine. Между сессиями продолжай по plan, evidence и snapshot; не возобновляй молча уже исчерпанный бюджет.

## Ошибки CLI

Успех — JSON stdout и exit 0. Недоступная private capability — JSON stdout и exit 2. Ошибки аргументов/данных/файлов — JSON stderr и exit 2. --help — обычная справка. CLI не запускает shell, тесты, модели, сеть или установки пакетов. Нет гонкоустойчивой изоляции против злонамеренного процесса с теми же файловыми правами.
