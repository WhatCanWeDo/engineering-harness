# Человеческий review

Review HTML генерируется по конкретному F0 hash и нейтральному run label. Он показывает контракт и экранированные текстовые previews (до 100 KB/файл); код из артефактов не исполняется. Для визуального продукта открой frozen HTML отдельно, оставив таймер review активным. Нет автоматического маскирования содержания: оно может раскрыть treatment. Coordinator видит mapping, reviewer получает только свою страницу.

1. Начни таймер непосредственно перед чтением. Чтение обязательного explanation/quiz входит в review.
2. При уходе/ожидании ставь паузу. Выбор режима review/repair/intervention возможен на паузе; интервалы не перекрываются.
3. Укажи pseudonym, номер просмотра задачи, prior exposure и unblinding. Personal crossover сохраняет carryover даже при случайном AB/BA. Для independent_reviewers один reviewer не должен видеть повтор/другой вариант той же задачи.
4. Каждый подтверждённый дефект получит issue ID; повторные repair rounds записывай в него, не добавляй новый issue. Clarifications без дефекта относятся к intervention time. Поле corrections считается только после полного review; interrupted/capped сохраняют затраченное время и observations, но summary остаётся null.
5. Заверши review как completed/abandoned/capped и скачай JSON. `ingest --kind review` связывает его с F0, проверяет последовательность events и сам считает секунды. Не оценивай за человека время или количество исправлений.

Состояние хранится в localStorage по run ID + artifact hash. При reload активный таймер ставится на паузу на последнем heartbeat (примерно секунда); вкладка не угадывает, думал ли пользователь между heartbeat и перезагрузкой. Переключение вкладок не ставит автоматическую паузу: reviewer может читать другой artifact. Есть напоминание, но browser idle — не измеритель умственной работы. При закрытии браузера export ещё не сделанных записей может быть потерян; сохраняй JSON.

LocalStorage привязан к origin. Для возвращения к незавершённому review используй ту же preview-сессию/URL; новый порт — другой origin. После экспорта JSON переносим и не зависит от preview. В MVP нет центрального review server и межустройственной синхронизации. Завершённый review immutable после ingest; до него браузер позволяет повторно скачать сохранённый export. Import не равнозначен подтверждению понимания quiz.

## Кликабельная выдача

```sh
python3 skills/understand-changes/scripts/preview.py /absolute/review-R.html
```

Выдай фактический `browser_link` после `verified_http:true`. Это однофайловый localhost preview, default TTL 2 часа. Report HTML открывается тем же способом. Сохрани путь постоянного HTML для повторного открытия. Не публикуй артефакты во внешнем hosting ради ссылки. При SSH сначала нужна явная доставка файла или разрешённый forwarding.
