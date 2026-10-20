(() => {
  const root = document.documentElement;
  try {
    const savedTheme = localStorage.getItem('reyminder-theme');
    if (savedTheme === 'dark' || savedTheme === 'light') root.dataset.theme = savedTheme;
  } catch (_) {}
  function updateThemeButtons() {
    const dark = root.dataset.theme === 'dark';
    document.querySelectorAll('[data-theme-icon]').forEach(el => el.textContent = dark ? '☀' : '☾');
    document.querySelectorAll('[data-theme-label]').forEach(el => el.textContent = dark ? 'Light mode' : 'Dark mode');
    document.querySelectorAll('[data-theme-toggle]').forEach(el => el.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode'));
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('reyminder-theme', root.dataset.theme); } catch (_) {}
    updateThemeButtons();
  }));
  updateThemeButtons();

  document.querySelectorAll('[data-password-toggle]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    const showing = input.type === 'password';
    input.type = showing ? 'text' : 'password';
    button.textContent = showing ? '◎' : '◉';
    button.setAttribute('aria-label', showing ? 'Hide password' : 'Show password');
    input.focus();
  }));

  // Gentle login interaction: indicate the form is being submitted without changing its behavior.
  document.querySelectorAll('.auth-card form').forEach(form => form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    if (button && form.checkValidity()) {
      button.classList.add('is-loading');
      button.dataset.originalText = button.textContent;
      button.textContent = 'Please wait…';
    }
  }));

  // Reminder list filters.
  document.querySelectorAll('[data-reminder-filter]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-reminder-filter]').forEach(item => item.classList.toggle('active', item === button));
    const filter = button.dataset.reminderFilter;
    document.querySelectorAll('#all-reminders [data-status]').forEach(item => {
      item.hidden = filter !== 'all' && item.dataset.status !== filter;
    });
  }));

  // Calendar works on both the dashboard and its own page.
  const daysEl = document.getElementById('calendar-days');
  const monthLabel = document.getElementById('calendar-month');
  if (daysEl && monthLabel) {
    let shown = new Date();
    shown = new Date(shown.getFullYear(), shown.getMonth(), 1);
    let selectedDate = new Date();
    const dataEl = document.getElementById('reminder-data');
    let reminders = [];
    try { reminders = JSON.parse(dataEl?.textContent || '[]'); } catch (_) {}
    const dateKey = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
    function showSelectedDay() {
      const key = dateKey(selectedDate);
      const label = document.getElementById('selected-date-label');
      const list = document.getElementById('selected-date-items');
      if (label) label.textContent = selectedDate.toLocaleDateString(undefined, {weekday:'long', month:'long', day:'numeric', year:'numeric'});
      if (!list) return;
      const matches = reminders.filter(item => item.due_at?.slice(0,10) === key);
      list.replaceChildren();
      if (!matches.length) { list.textContent = 'No reminders scheduled for this day.'; return; }
      matches.forEach(item => {
        const line = document.createElement('div'); line.className = 'calendar-reminder-line';
        const dot = document.createElement('span'); dot.className = 'legend-dot legend-reminder';
        const content = document.createElement('span');
        const title = document.createElement('strong'); title.textContent = item.title;
        const time = document.createElement('small'); time.textContent = ` ${item.due_at.slice(11,16)} · ${item.completed ? 'Completed' : item.category || 'To do'}`;
        content.append(title, time); line.append(dot, content); list.appendChild(line);
      });
    }
    function renderCalendar() {
      monthLabel.textContent = shown.toLocaleDateString(undefined, {month:'long', year:'numeric'});
      daysEl.replaceChildren();
      const firstWeekday = new Date(shown.getFullYear(), shown.getMonth(), 1).getDay();
      const daysInMonth = new Date(shown.getFullYear(), shown.getMonth()+1, 0).getDate();
      const todayKey = dateKey(new Date());
      for (let i=0; i<firstWeekday; i++) { const blank = document.createElement('span'); blank.className = 'calendar-blank'; daysEl.appendChild(blank); }
      for (let day=1; day<=daysInMonth; day++) {
        const date = new Date(shown.getFullYear(), shown.getMonth(), day); const key = dateKey(date);
        const button = document.createElement('button'); button.type = 'button'; button.className = 'calendar-day'; button.textContent = day;
        if (key === todayKey) button.classList.add('is-today');
        if (key === dateKey(selectedDate)) button.classList.add('is-selected');
        if (reminders.some(item => item.due_at?.slice(0,10) === key)) button.classList.add('has-reminder');
        button.setAttribute('aria-label', date.toLocaleDateString());
        button.addEventListener('click', () => { selectedDate = date; renderCalendar(); showSelectedDay(); });
        daysEl.appendChild(button);
      }
    }
    document.getElementById('prev-month')?.addEventListener('click', () => { shown = new Date(shown.getFullYear(), shown.getMonth()-1, 1); renderCalendar(); });
    document.getElementById('next-month')?.addEventListener('click', () => { shown = new Date(shown.getFullYear(), shown.getMonth()+1, 1); renderCalendar(); });
    document.getElementById('today-month')?.addEventListener('click', () => { shown = new Date(new Date().getFullYear(), new Date().getMonth(), 1); selectedDate = new Date(); renderCalendar(); showSelectedDay(); });
    renderCalendar(); showSelectedDay();
  }

  const dueInput = document.getElementById('due_at');
  if (dueInput && !dueInput.value) {
    const later = new Date(Date.now() + 60*60*1000);
    later.setMinutes(Math.ceil(later.getMinutes()/5)*5, 0, 0);
    const local = new Date(later.getTime() - later.getTimezoneOffset()*60000);
    dueInput.value = local.toISOString().slice(0,16);
  }
})();
