
'use strict';
const quiz = JSON.parse(document.getElementById('quiz-data').textContent);
const root = document.getElementById('questions');
quiz.forEach((q, index) => {
  const field = document.createElement('fieldset');
  const legend = document.createElement('legend');
  legend.textContent = `${index + 1}. ${q.question}`;
  field.append(legend);
  const feedback = document.createElement('div');
  feedback.className = 'feedback';
  feedback.hidden = true;
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  const buttons = [];
  q.options.forEach((option, optionIndex) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `${String.fromCharCode(65 + optionIndex)}. ${option.text}`;
    button.setAttribute('aria-pressed', 'false');
    buttons.push(button);
    button.addEventListener('click', () => {
      buttons.forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      feedback.replaceChildren();
      const verdict = document.createElement('strong');
      verdict.textContent = option.id === q.correct_option_id ? 'Верно.' : 'Не совсем.';
      const reason = document.createElement('p');
      reason.textContent = option.explanation;
      feedback.append(verdict, reason);
      if (option.id !== q.correct_option_id) {
        const correct = q.options.find(o => o.id === q.correct_option_id);
        const answer = document.createElement('p');
        answer.textContent = `Правильный ответ: ${correct.text} ${correct.explanation}`;
        feedback.append(answer);
      }
      feedback.hidden = false;
    });
    field.append(button);
  });
  field.append(feedback);
  root.append(field);
});
