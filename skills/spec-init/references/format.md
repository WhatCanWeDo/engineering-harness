# ML Task Spec v1

Канонический файл — `spec.json` UTF-8. `SPEC.md` и `review.html` генерируются из одной ревизии; manifest хранит SHA-256 исходного документа и файлов. Renderer всегда пишет **draft**: прохождение validation, quiz или отметки в HTML не означают согласования. Полноту и корректность смысла оценивает человек.

## Фиксированные разделы

1. **intent** — проблема, потребитель, исходный и желаемый сценарий, deliverable; продуктовый успех отдельно от ML surrogate.
2. **context** — что уже существует, paths/services, происхождение фактов, свежесть/противоречия, границы системы.
3. **scope** — in/out, пользовательские сценарии, non-goals и внешние ограничения.
4. **requirements** — проверяемые R-ID и связанная матрица AC-ID.
5. **data** — версии/схемы/labels, источники/доступ, train/validation/test, temporal/entity leakage, slices и качество.
6. **approach** — baseline (в том числе без ML), выбранный вариант, альтернативы, интерфейсы и схема.
7. **evaluation** — гипотеза, определения метрик, протокол и datasets/slices, повторения/seeds/неопределённость, stop rule, бюджет поиска по holdout. Для private отмечай реальную доступность защищённой среды; skill не генерирует тесты.
8. **reproducibility** — версии кода/данных/model/config/environment, hardware, команды воспроизведения, lineage и outputs.
9. **resources** — потребности CPU/GPU/VRAM/RAM/disk, latency/throughput если нужны, time/cost/network, оценки vs измерения, ограничения/остановка.
10. **operations** — deployment, monitoring/drift, rollback, владельцы, доступ. Для offline исследования поясни неприменимость.
11. **delivery** — этапы, зависимости, минимальный сквозной шаг, артефакты и передача исполнителям.
12. **risks** — допущения, failure modes, последствия, mitigations и решения к обсуждению.

Все 12 разделов присутствуют всегда. Неприменимая часть получает not_applicable с содержательной причиной. При исследовании успешное выполнение протокола и улучшение модели — разные исходы. Не обещай второе как обязательный результат, если задача состоит в проверке гипотезы.

## Поля

Точный контракт проверяется `scripts/contract.py`; готовый пример — [ML retrieval task](../assets/ml-example.json). Scaffold создаёт структуру, которую нужно наполнить, а не валидный готовый результат.

- `version:1`, `spec_id` стабильный, `revision` положительное целое, `project_id`, `title`, `request` (исходный запрос), `summary` (как понят результат).
- `scouting`: `status` ready / empty / unavailable; `task_id`, `packet_id`, `notes` (snapshot, полнота, freshness, caveats). Для ready/empty builder требует `--packet`: проверяет task/packet/role, project scope и наличие использованных K-ID@revision. Это согласованность артефактов, не доказательство независимости Scout. При unavailable notes объясняет причину, packet_id пустой, источников knowledge нет.
- `sources`: `{id, kind:user|knowledge|code|web|artifact, locator, note}`. Knowledge locator — точный `K-...@N` из packet. Web — HTTP(S) URL. User source может ссылаться на исходный запрос или конкретный ответ пользователя. Code source включает путь/символ и ревизию/hash, если они доступны. Источник может поддерживать факт; не объявляй весь spec подтверждённым.
- `sections`: ровно 12 `{id, items}` в порядке выше. Item: `{text, status, source_ids, gap_ids}`.
- `requirements`: `{id, text, status, source_ids, gap_ids}`. ID сохраняются между ревизиями; отозванное требование объясняется при ревью, не используется для другого смысла.
- `acceptance`: `{id, requirement_ids, measure, method, threshold, artifact, status, source_ids, gap_ids}`. Покрывает все R-ID. `method` включает dataset/slice и условия измерения; `threshold` — число/условие или честное «не задано» с unknown и gap. Критерий по качеству без согласованного порога не получает выдуманного default.
- `gaps`: `{id, missing, resolution, basis, impact, blocking:boolean, status:open|proposed|confirmed, question}`. `resolution` объясняет выбранный для черновика способ обойти пробел или причину отсрочки; не оставляй «TBD» без последствий. `basis` для confirmed содержит ID реального user source отдельным словом. Unknown items/R/AC обязаны ссылаться на gap. Proposed choice не равно confirmed requirement. Подтверждённый gap сохраняется как история; связанные утверждения/критерии обновляются по ответу пользователя.
- `diagrams`: 1–2 `{title, description, nodes, edges}`. Node: `{id,label,detail,state:existing|proposed|external}`. Edge: `{from,to,label}`. На схеме 2–9 узлов, до 12 связей; все узлы связаны. Разбивай большую систему на обзор и zoom, а не уменьшай шрифт. `label` до 55 символов, `detail` до 160; ещё длиннее — в текст спецификации. Покажи именно систему из запроса. Изменяемый узел — proposed, его существующая часть уточняется в description. Это обзор, не полный call graph.
- `quiz`: ровно 5 вопросов по контракту understand-changes (`id,concept,question,options[{id,text,explanation}],correct_option_id`). Формулируй «по этому черновику», когда проверяется предложенный подход. Не задавай вопросы на угадывание неподтверждённых желаний пользователя.

Статусы утверждений: `user_statement` (есть user source), `evidence` (есть источник, который нужно оценить), `proposal`, `unknown` (есть gap), `not_applicable` (причина в text). Ссылки проверяются; семантическую обоснованность статуса script не доказывает. Все тексты plain text: Markdown/HTML внутри полей не исполняется. Не клади secrets/private evals в артефакты.

## Review и изменения

HTML показывает overview, все gaps с временными решениями, 12 разделов, R → AC, источники, поля для замечаний и quiz. Замечания и отметки автоматически собираются в отдельном текстовом блоке с ID/revision/digest. Пользователь копирует его кнопкой «Скопировать» или вручную и вставляет в чат; скачивания TXT нет. Если clipboard недоступен, кнопка выделяет текст и показывает сочетание клавиш. Они не сохраняются после закрытия вкладки и не отправляются автоматически; пользователь передаёт их в чат. Статус approved не записывается кнопкой.

Новая постановка/ответ → новая revision в новом каталоге. Перед передачей в реализацию зафиксируй явно согласованный пользователем ID/revision/digest и оставшиеся риски. Реализация получает новый task_id и актуальный контекст, при этом спеку читает напрямую. Initial public/private/adversarial тестирование остаётся отдельным явно запрошенным workflow.

Пример вызова:

```sh
python3 skills/spec-init/scripts/spec.py validate draft.json
python3 skills/spec-init/scripts/spec.py build draft.json --packet context-packet.json --output docs/specs/TASK/r1
python3 skills/understand-changes/scripts/preview.py docs/specs/TASK/r1/review.html
```

Для unavailable примера packet опускается. `build --quiz-from PREVIOUS/review.html` разрешён для правки представления с неизменным quiz; случайный порядок не перегенерируется ради красивого распределения.
