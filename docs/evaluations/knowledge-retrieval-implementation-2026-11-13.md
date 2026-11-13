# Knowledge retrieval: реализованный пилот и проверки

2026-11-13. Пользователь одобрил реализацию плана r1 сообщением «делай».
Baseline `5856756`; финальный Core snapshot `4a638484daa05e1fc785b0048caef661e2e1d5bf8a555151a052ed759ff8c264`.
Исследовательская спецификация и результаты до реализации сохранены отдельно.

Semantic scoring теперь переиспользует проверенные нормализованные векторы и NumPy matrix.
Кэш ограничен connection и фактическими index rows; scope, роли, snapshot, TTL/dependencies
и текущий отзыв проверяются заново. NumPy optional: stdlib path работает отдельно.
Первый одиночный cached-query CLI не платит за импорт NumPy: matrix promotion выполняется
на reuse либо при уже загруженном embedding backend. Disk schema vectors остаётся JSON.

Добавлены QueryPlan validation, original+conditional rewrite, bounded fusion и DB-owned
candidate pool, native rerank/filter/abstention, повторная проверка refs и trace в packet.
Новые команды `workflow start --retrieval staged`, `workflow retrieve`, `workflow rerank`.
Skill использует staged явно, старые CLI callers сохраняют legacy. Decomposition и HyDE
только через explicit experimental flag; HyDE использует document encoder, не создаёт facts.
Core не вызывает LLM сам. Обновлены skill, Claude worker/wrappers и установленные адаптеры
Codex/Claude; installer doctor ready, без warnings/errors. Полный Rust rewrite не выполнялся.

## Фактически выполненные проверки

- **154 tests PASS** в окончательном полном regression run, 17.424 s, source stable.
- Initial target public suite (19 tests) был зафиксирован отдельным автором до чтения
  implementation. 19/19 PASS; отдельный subprocess без NumPy: 5/5 PASS, отсутствие
  numpy.* проверено до/после. Это повтор проверок, не дополнительные уникальные tests.
- Паритет old/new: 192 cold cases, 12 vector perturbations, 48 unique warm cases;
  0 расхождений ID/status/mode на этих данных. Преднамеренное исключение — исправленный
  malformed JSON vector case, который старый код ошибочно принимал.
- Отдельный adversarial worker обнаружил унаследованное принятие JSON строки/объекта
  как вектора. Исправлено; постоянный regression `tests/test_retrieval_adversarial.py`.
  Frozen final suite 11/11 и минимальный reproducer PASS; initial fail сохранён.
  Это ограниченная проверка, не доказательство отсутствия всех ошибок. Private unavailable.
- Реальный native smoke: свежие planner и reranker, без qrels/плана в rerank brief.
  Planner оставил ясный запрос без rewrite; из 20 кандидатов выбраны две нужные записи
  (offset и dlq), packet сохранён. Независимый evaluator проверил bindings, digest,
  membership/order, source provenance, текущую доступность, token budget и audit trace.
  Это один интеграционный сценарий, не новая оценка общего качества.

## Скорость

Последовательный paired workload, те же frozen corpus/model vectors, восемь одинаковых
запросов × три повтора на режим/размер (n=24). Тёплый процесс/query cache; время LLM и
загрузка модели исключены. Значения в миллисекундах, baseline → final.

| Записей | Режим | Median | p95 |
|---:|---|---:|---:|
| 100 | lexical | 1.71 → 1.55 | 2.95 → 2.63 |
| 100 | semantic | 17.44 → 2.85 | 19.08 → 4.55 |
| 100 | hybrid | 19.61 → 4.69 | 21.70 → 6.33 |
| 1000 | lexical | 11.42 → 12.09 | 15.29 → 22.19 |
| 1000 | semantic | 156.63 → 17.45 | 166.15 → 27.36 |
| 1000 | hybrid | 171.78 → 31.09 | 197.73 → 41.30 |

Semantic на1000 ускорился примерно в9 раз, hybrid в5.5 раза. Lexical1000 не улучшился:
median +5.84%, p95 +45.1%; этот результат сохранён, причины не приписываются языку
или алгоритму без отдельного исследования. P95 чувствителен к короткому n=24.

Fresh-process CLI измерен отдельно (n=3/ячейку, warm OS cache, bundle validation включена).
До lazy promotion cached semantic100 замедлялся 187.26→211.34ms; это сохранённый
промежуточный результат и основание исправления. После него100:185.70→184.88ms,
1000:327.04→326.57ms — различие в пределах шума, а не обещание ускорения CLI.
Uncached embedding:100:1201.78→1178.05ms,1000:1348.98→1304.56ms; при n=3 нельзя
обобщать небольшую разницу. Warm gain не переносится на одиночный cold запрос.

Peak RSS worker около1.23GiB. Поиск по большим file-dependency графам, concurrency/load,
production native LLM latency/cost и другой cross-encoder не оценены. Corpus synthetic;
значения качества из предыдущего исследования не объявлены новой независимой оценкой.

## Артефакты и использование

[Сводка и холодные/тёплые измерения](../../evals/knowledge-retrieval/2026-11-13/implementation/summary.json),
[regression receipt](../../evals/knowledge-retrieval/2026-11-13/implementation/regression-receipt.json),
[native smoke](../../evals/knowledge-retrieval/2026-11-13/implementation/native-smoke.json),
[manifest](../../evals/knowledge-retrieval/2026-11-13/implementation/manifest.json).
Raw inputs, per-query traces, execution commands, old failures и snapshots остаются локально
в `.harness/testing/retrieval-impl-2026-11-13`. Основная переносимая regression команда:
`.venv/bin/python -m unittest discover -s tests -v` (preview tests требуют loopback).

[Skill и CLI протокол](../../skills/knowledge-cycle/references/retrieval.md),
[обзор архитектуры и ограничения](../rfcs/007-staged-retrieval.md).
Схема есть в RFC; проверка отображения не выполнялась по указанию пользователя.
