# Knowledge MVP1 / MVP2 — фактическая оценка

Дата: 2026-11-03. Локальный cooperative profile; private evaluation **unavailable**. Тесты создавались отдельными агентами с минимальными briefs. Pre-implementation public suites и post-hoc adversarial provenance не смешиваются. Публичные исправления после атаки — adaptive regressions, не новый holdout.

## MVP1 gate

34 public tests (28 Core + 6 workflow) подготовлены по открытому контракту. Затем независимый adversarial-автор на frozen candidate нашёл коллизию составного idempotency key: `(a:b,c)` и `(a,b:c)` превращались в одинаковую строку. Ключ заменён структурированным JSON; lookup дополнительно проверяет task/kind. Финал MVP1: **47/47 pass**, только после этого начат MVP2.

- [Public provenance](../../evals/knowledge-mvp/2026-11-03/public-contract.json).
- [Первоначальная adversarial-находка](../../evals/knowledge-mvp/2026-11-03/mvp1/adversarial.json).
- [Исправленный gate](../../evals/knowledge-mvp/2026-11-03/mvp1/gate-fixed/receipt.json).

## MVP2 gate

21 public test создан до реализации semantic. Отдельный author также зафиксировал 18 documents / 14 queries с qrels, SHA256 corpus `34e67593025203e7dc9dea24aef750c4b22380b29ca353a9e862db25b05761fe`. Synthetic providers проверяют алгоритмическое поведение; реальная модель проверена отдельно.

Adversarial-автор добавил 6 проверок; нашёл 4 ошибки: отсутствие provider ошибочно давало semantic/empty на пустом корпусе; malformed manifest мог выйти необработанным исключением; неучтённый runtime config не менял model identity; subnormal vectors неверно нормализовались. Исправлены fallback ordering, validation manifest и полноты файлов, нормализация через предварительное масштабирование. Две проверки interleaving изменений прошли на исходном candidate.

**Финал: 114/114 тестов pass** — 74 knowledge + 40 существующих проверок skills. Реальный embedding benchmark pass. Skill structural validator pass. Перед/после suites проверена стабильность файлов; source hashes и команды в receipt.

- [MVP2 public provenance](../../evals/knowledge-mvp/2026-11-03/mvp2/public-contract.json).
- [Первоначальные adversarial findings](../../evals/knowledge-mvp/2026-11-03/mvp2/adversarial.json).
- [Финальный gate](../../evals/knowledge-mvp/2026-11-03/mvp2/gate-final/receipt.json).
- [Benchmark — каждый запрос и timings](../../evals/knowledge-mvp/2026-11-03/mvp2/benchmark-final/results.json).

## Реальный retrieval

| Режим | Recall@3 | MRR@3 |
|---|---:|---:|
| Lexical | 0.500 | 0.464 |
| Semantic | 1.000 | 1.000 |
| Hybrid RRF | 0.643 | 0.607 |

Модель FastEmbed multilingual MiniLM, ONNX, 384 dimensions. HF revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`; bundle identity включает hashes файлов, runtime и chunk policy. Реальный inference выполнялся локально. Установлены FastEmbed 0.9.1 и ONNX Runtime 1.31.1; зависимости зафиксированы в uv.lock. До готовности native profile установлен явно, обычные задачи модель не скачивают.

По этому development-сравнению для локального пилота включён semantic. Corpus/qrels и ranking weights после измерения не менялись. Это адаптивный выбор default, а не доказательство качества на независимом holdout. Hybrid объединяет ranks с равными весами (RRF k=60); слабые lexical совпадения иногда вытесняют релевантный semantic source. Это показано в per-query results, а не спрятано.

Timings не следует сравнивать как изолированный эксперимент latency: semantic выполняется до hybrid, и hybrid использует кеш query vector. Cold index timing включает загрузку модели; large-corpus p95, writer stress, task success и реальные сэкономленные agent tokens не измерены.

## Повторение

```sh
uv sync --extra semantic --locked
.venv/bin/python scripts/check_knowledge.py --stage all --output /new/check-directory
.venv/bin/python scripts/benchmark_knowledge.py --corpus evals/knowledge-mvp/2026-11-03/mvp2/retrieval-corpus.json --model /existing/local/bundle --output /new/benchmark-directory
```

Новый output directory обязателен: прежний результат не перезаписывается. Ссылки и команды относятся к рабочему репозиторию без commit baseline; идентичность проверенного кода задаётся хешами receipt и frozen snapshots.

## Ограничения

Нет защищённого private evaluator и отдельного service principal; общий filesystem не защищён от своего владельца. Полный process-kill/stress цикл и live Claude integration не проверялись. Native instructions не обеспечивают обязательный вызов после любого свободного сообщения. Автоматическое semantic dedup, обнаружение противоречий, полноценный purge/retention и интеграция Obsidian остаются за пределами этих MVP. Context packet не может отозвать текст, уже прочитанный LLM.

## Native cycle pilot

Первый свежий Curator получил ограниченный brief и вернул 3 project proposals: 2 дословных source excerpts committed, 1 benchmark candidate. Curation complete, pending queue пуста. Другой свежий Scout на изолированной SQLite-копии выбрал один релевантный источник для новой цели; compiler собрал пакет в пределах бюджета. Это один Codex collaboration pilot, не live Claude evaluation. [Квитанция](../../evals/knowledge-mvp/2026-11-03/mvp2/native-cycle.json), [HTML QA](../../evals/knowledge-mvp/2026-11-03/mvp2/html-qa.json).
