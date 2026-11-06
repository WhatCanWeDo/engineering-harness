# Локальный A/B протокол v1

Каноническая реализация: `harness/ab`. `python3 skills/harness-ab/scripts/ab.py` эквивалентен `python3 -m harness ab`; установленный console entrypoint — `harness ab`. Ни одна команда не вызывает модель. Входной JSON ограничен 8 MiB, explicit file lists включают dirty/untracked файлы. Снимки — реальные копии с SHA-256 и executable bit; symlinks исключены. Большие данные лучше идентифицировать в environment manifest и использовать внешнюю read-only среду; MVP не является object store.

## План

```sh
harness ab plan --input plan.json --output .harness/ab/EXPERIMENT
harness ab prepare --experiment .harness/ab/EXPERIMENT
harness ab dispatch --experiment .harness/ab/EXPERIMENT
```

`plan` требует новый output. Пути `root`, `knowledge_db`, evaluator `path` указывай абсолютными. `files` — явные относительные пути без traversal/symlinks. Не включай `.env`, credentials, private suites или весь HOME.

Обязательные поля `plan.json`:

| Поле | Значение |
|---|---|
| version | 1 |
| hypothesis | Проверяемое утверждение с областью применимости |
| dataset / dataset_provenance | development или fresh_validation; происхождение и прошлое использование |
| baseline / candidate | Config objects, см. ниже |
| allowed_changes | Точное множество изменившихся JSON pointers effective configuration; например `/files/SKILL.md/sha256` |
| tasks | Непустой список Task objects |
| replicates / seed | Целое 1..100; явный seed расписания |
| retry_policy | none; retries не выбираются внутри experiment |
| analysis | `{ "primary":"human_seconds", "min_improvement":10, "max_correctness_regressions":0 }`; primary также cost, threshold в единицах метрики |
| review | `{ "protocol":"personal_crossover", "replicates":[1] }`; альтернатива independent_reviewers; [] допустим при cost-primary, но human effect не измерен |
| limits | max_runs, wall_seconds_per_run, calls_per_run, human_seconds_per_review; положительные значения |
| knowledge_db | Опциональный путь к уже существующей SQLite, backup фиксируется до всего experiment |
| synthetic | По умолчанию false. true принудительно маркирует любой результат synthetic_demonstration |

Config: `root`, `files`, `agent`, `agent_version`, `model`, `reasoning`, `environment`, `permissions`, `tools`, `instructions`, `cache_policy`, `model_control`. Все поля кроме root/files входят в effective config; file list преобразуется в hashes. Версии агента/модели/reasoning у A/B должны совпадать. Если alias нельзя закрепить, укажи это в model_control. Native registration files и общие инструкции тоже включаются в scope. Единственное объявленное изменение может быть пакетом файлов — вывод тогда относится ко всему пакету.

Task: `id`, `goal`, `clarification_policy`, `requirements` (уникальные непустые IDs), `root`, `files`, `evaluator`. Task files и config files не должны пересекаться. Actual snapshot scope задаёт file list; автоматический сбор всех Git/untracked/ignored files отсутствует.

Command evaluator:

```json
{"kind":"command","identity":"acceptance-v1","independent":true,
 "path":"/absolute/path/to/evaluator.py",
 "argv":["python3","{evaluator}","{output}","{result}"],
 "timeout_seconds":120}
```

Копия evaluator заморожена отдельно от developer workspace. argv запускается без shell; placeholders заменяются путями. Evaluator пишет `{result}` JSON: `{"checks":[{"requirement_id":"R1","verdict":"pass","severity":"none","evidence":"фактический результат проверки"}]}`. Требуется ровно один check на каждый requirement. Verdict pass/fail/error/unavailable; severity none/minor/major/critical. Exit code 0 без JSON не означает pass. Timeout/nonzero/missing result создаёт error checks. stdout/stderr сохраняются, повторный скрытый запуск запрещён. Malformed JSON/невозможный process launch оставляет попытку в evaluation-attempts; исправление требует нового experiment.

Внешний evaluator: `{"kind":"external","identity":"rubric-v1","independent":true,"protected":false}`. Результат импортирует coordinator; локальный CLI валидирует identity/hash/формат, а не доказывает независимость автора. Sandbox для evaluator отсутствует: он работает с правами локального процесса. Запускай лишь согласованный evaluator. Защищённый backend этим форматом не имитируется.

`prepare` создаёт assignment, workspace и SQLite для каждого run. При отсутствии исходной KB базы пустые. Если KB передана, каждая ветка получает один и тот же backup. Для knowledge-cycle обязательно явное `--db assignment.knowledge_db` до команды; native memory вне CLI контролирует adapter. Один prepared assignment = один fresh session. Повторный dispatch до получения receipt возвращает тот же assignment. После получения terminal receipt выдаётся следующий; порядок нельзя ускорять параллельными runs с общей машиной без нового протокола.

## Outputs и receipts

```sh
harness ab freeze --experiment E --run R --source /absolute/workspace --files files.json
harness ab receipt --experiment E --run R > execution.json
# Заполнить фактические значения, затем:
harness ab ingest --experiment E --kind execution --input execution.json
harness ab ingest --experiment E --kind usage --input usage.json
harness ab evaluate --experiment E --run R
```

`files.json` — массив имён результатов, например `["src/tool.py","result.md"]`. F0 immutable; `--revision F1` после execution receipt создаёт отдельный repair output и допускает отдельную evaluation. Уже существующая revision не перезаписывается. Исходные файлы workspace могут меняться, frozen snapshot остаётся прежним.

Execution receipt scaffold содержит run_id/config_sha256/output_sha256, status, duration_seconds, session_id, fresh_session, isolation, isolation_evidence, skill_loading_evidence, accounting_complete, request_keys. Заполни null/empty фактическими значениями. status: completed/timeout/budget_exhausted/infra_error/aborted. У completed обязателен F0 hash; failed run может иметь null output. `isolation`: attested/unavailable/violated; attested означает свидетельство native adapter, не внешнюю security guarantee. Session ID нельзя повторно использовать между runs.

`request_keys`: полная ожидаемая инвентаризация F0 вызовов `[ ["provider", "request_id"] ]`, включая attributable sidecars. `accounting_complete:true` ставь только при реальной полноте. Usage можно импортировать до/после execution; отчёт сопоставляет inventory с records. Несовпадение не превращается в нулевую стоимость.

Usage example:

```json
{"run_id":"R","provider":"provider","request_id":"request-123",
 "phase":"f0","category":"sidecar","basis":"unknown","money":null,
 "units":{"input_tokens":1200,"output_tokens":500}}
```

phase f0/repair/overhead; category main/sidecar/compute/evaluation/setup/report. Shared overhead имеет `run_id:null`. Реальные суммы требуют basis reported/estimated, currency и pricing_provenance; unknown требует money:null. Unit values неотрицательны или null. Current pricing не зашито. Request key глобально уникален внутри experiment по структурированной паре provider/request_id; дубликат с тем же payload идемпотентен, с другим — ошибка. Подписка без billable marginal price остаётся unknown.

External evaluation receipt: run_id, revision F0/F1, output_sha256, evaluator_sha256 = canonical SHA-256 evaluator object из plan.json, provenance independent_external, protected false, checks. Command evaluation формирует это автоматически. Для внешних receipts используй `harness.ab.core.digest` вместо самодельного сериализатора.

## Отчёт и завершение

```sh
harness ab review --experiment E --run R --output review-R.html
harness ab ingest --experiment E --kind review --input /path/to/downloaded-review.json
harness ab status --experiment E
harness ab report --experiment E --output /new/report-directory
harness ab close --experiment E --reason 'completed or explicit early stop'
```

Report directory новый; повторная сборка из тех же inputs/records даёт те же JSON и HTML. comparison.json хранит детали, HTML — обзор. Report доступен в любой момент, не закрывает эксперимент. close останавливает новые mutations, в том числе usage; импортируй поздние invoices до close. Read-only отчёты после close доступны. Ранняя остановка сохраняет все planned denominators. Для исправления records — новый experiment с provenance, старые данные не переписываются.

Decision порядок: integrity violation→invalid; A-pass/B-fail→regression_observed; missing correctness/primary/planned review/cost→incomplete; unavailable isolation, both-fail или недостаточный выигрыш→inconclusive; достаточный dev эффект→promising_on_dev; fresh-validation→recommend_pilot. Human time = review+repair+intervention в границах recorder. Task-level среднее содержит все повторы; неполная задача не даёт summary delta. Никаких p-values, equivalence proof или auto-install.

Native sessions не контролируются процессом CLI: лимиты calls/time/money advisory. В MVP нет автоматического currency conversion, retries, multi-agent/model strata, защищённой проверки и автоматического мониторинга глобальной памяти. Общие расходы показываются как известный subtotal без гарантии полноты, а не как полная цена эксперимента.

## Воспроизводимый технический пример

`python3 scripts/demo_harness_ab.py --output /new/demo-directory` создаёт синтетические inputs/receipts, четыре simulated runs, review pages и два отчёта. Он не вызывает моделей и не измеряет человека. `synthetic:true` и fixture provenance сохраняются во всех inputs; итог всегда synthetic_demonstration. Это пример использования и smoke validation транспорта, не независимый suite качества и не benchmark skills.
