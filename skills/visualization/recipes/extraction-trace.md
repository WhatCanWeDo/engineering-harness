# Источник → извлечение → результат

Три связанные панели: inert source snapshot, trace, итоговые fields. По выбору поля подсвечивай
точный node/span, показывай selector/path, число matches, raw value, реальные transforms и output.
Покажи timestamp/hash источника и различай raw response от rendered DOM. При отсутствии геометрии
используй DOM/text представление, а не выдуманную подсветку поверх screenshot.

Ноль matches — missing; несколько — ambiguity или фактическое правило выбора. После изменения
source прежний output считается stale до настоящего перерасчёта. Самописный JS-аналог production
парсера не является trace реального кода. Если trace нет, предложи отдельный replay extractor
на сохранённом snapshot, а до него покажи только имеющиеся артефакты.

Никогда не вставляй внешний HTML как доверенный исполняемый документ. Escaping/inert text,
отсутствие handlers/scripts/network, явная redaction map с сохранённой привязкой trace.
Проверь один успешный, missing и неоднозначный пример, если они доступны.
