---
name: harness-ab
description: По запросу сравнить baseline и candidate skill на одинаковых задачах.
disable-model-invocation: true
---

Прочитай канонический [harness-ab](../../../skills/harness-ab/SKILL.md) и выполни запрос: $ARGUMENTS.

Пути разрешай от `skills/harness-ab`. Общая логика — CLI/Core; этот entrypoint не создаёт собственного agent loop. Native execution protocol: references/native-adapters.md.
