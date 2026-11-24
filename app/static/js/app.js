/**
 * Comportements de l'interface. Aucun script en ligne dans les gabarits (CSP « script-src 'self' »).
 *  - menu mobile (tiroir)              [data-menu-toggle] / [data-menu-close]
 *  - recherche et filtres dynamiques   form[data-live-search] + [data-live-results] (+ [data-live-sync][id])
 *  - confirmation avant envoi          form[data-confirm="…"]
 *  - lignes de tableau cliquables      tr[data-href]
 *  - règles de mot de passe en direct  [data-pwd-rules] (champ [data-pwd-new], confirmation [data-pwd-confirm])
 *  - jeton CSRF pour fetch()           window.appFetch(url, options)
 */

function initMenu() {
  const shell = document.querySelector('.shell');
  if (!shell) return;
  const toggles = document.querySelectorAll('[data-menu-toggle]');
  const set = (open) => {
    shell.classList.toggle('shell--menu-open', open);
    toggles.forEach((btn) => btn.setAttribute('aria-expanded', String(open)));
    document.body.style.overflow = open ? 'hidden' : '';
  };
  toggles.forEach((btn) =>
    btn.addEventListener('click', () => set(!shell.classList.contains('shell--menu-open'))),
  );
  document.querySelectorAll('[data-menu-close]').forEach((el) => el.addEventListener('click', () => set(false)));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') set(false);
  });
  window.matchMedia('(min-width: 1024px)').addEventListener('change', (event) => {
    if (event.matches) set(false);
  });
}

function initLiveSearch() {
  document.querySelectorAll('form[data-live-search]').forEach((form) => {
    const zone = () => document.querySelector('[data-live-results]');
    if (!zone()) return;
    const clear = form.querySelector('[data-live-clear]');
    const isText = (el) => el.matches('input[type="search"], input[type="text"], input:not([type])');

    const buildUrl = () => {
      const url = new URL(form.getAttribute('action') || window.location.pathname, window.location.origin);
      for (const [key, value] of new FormData(form)) {
        if (String(value).trim() !== '') url.searchParams.append(key, String(value).trim());
      }
      return url;
    };

    let timer = null;
    let controller = null;
    let last = buildUrl().toString();

    const syncClear = () => {
      if (clear) clear.hidden = ![...form.querySelectorAll('input[type="search"]')].some((el) => el.value.trim());
    };

    const run = async (force = false) => {
      const url = buildUrl();
      if (!force && url.toString() === last) return;
      last = url.toString();
      controller?.abort();
      controller = new AbortController();
      zone().setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { 'X-Requested-With': 'live-search' },
        });
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const fresh = doc.querySelector('[data-live-results]');
        if (fresh) zone().replaceWith(fresh);
        document.querySelectorAll('[data-live-sync][id]').forEach((el) => {
          const twin = doc.getElementById(el.id);
          if (twin) el.replaceWith(twin);
        });
        window.history.replaceState(null, '', url);
        syncClear();
      } catch (error) {
        if (error.name !== 'AbortError') form.submit(); // repli : rechargement classique
      } finally {
        zone()?.removeAttribute('aria-busy');
      }
    };

    form.addEventListener('input', (event) => {
      if (!isText(event.target)) return;
      clearTimeout(timer);
      syncClear();
      if (event.target.value.trim().length === 1) return; // un seul caractère : on attend la suite
      timer = setTimeout(run, 300);
    });
    form.addEventListener('change', (event) => {
      if (isText(event.target)) return;
      clearTimeout(timer);
      run();
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      clearTimeout(timer);
      run(true);
    });
    clear?.addEventListener('click', (event) => {
      event.preventDefault();
      form.querySelectorAll('input[type="search"]').forEach((el) => {
        el.value = '';
      });
      form.querySelector('input[type="search"]')?.focus();
      clearTimeout(timer);
      run();
    });
    syncClear();
  });
}

function initConfirmations() {
  document.addEventListener('submit', (event) => {
    const message = event.target.dataset?.confirm;
    if (message && !window.confirm(message)) event.preventDefault();
  });
}

function initRowLinks() {
  document.addEventListener('click', (event) => {
    if (event.target.closest('a, button, input, select, textarea, label')) return;
    const row = event.target.closest('tr[data-href]');
    if (row?.dataset.href) window.location.href = row.dataset.href;
  });
}

function initPasswordRules() {
  document.querySelectorAll('[data-pwd-rules]').forEach((box) => {
    const form = box.closest('form');
    const input = form?.querySelector('[data-pwd-new]');
    const confirm = form?.querySelector('[data-pwd-confirm]');
    if (!input) return;
    const min = Number(box.dataset.minLength || 12);
    const tests = {
      length: (v) => v.length >= min,
      upper: (v) => /[A-Z]/.test(v),
      lower: (v) => /[a-z]/.test(v),
      digit: (v) => /[0-9]/.test(v),
      special: (v) => /[^A-Za-z0-9]/.test(v),
      match: (v) => !confirm || (v !== '' && v === confirm.value),
    };
    const update = () => {
      const value = input.value;
      box.hidden = value === '' && (!confirm || confirm.value === '');
      box.querySelectorAll('[data-rule]').forEach((li) => {
        li.classList.toggle('is-ok', Boolean(tests[li.dataset.rule]?.(value)));
      });
    };
    input.addEventListener('input', update);
    confirm?.addEventListener('input', update);
    update();
  });
}

/** fetch() avec le jeton CSRF de la page (balise <meta name="csrf-token">), pour les appels à /api/… */
window.appFetch = (url, options = {}) => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content ?? '';
  const headers = new Headers(options.headers || {});
  headers.set('X-CSRF-Token', token);
  headers.set('Accept', 'application/json');
  return fetch(url, { credentials: 'same-origin', ...options, headers });
};

initMenu();
initLiveSearch();
initConfirmations();
initRowLinks();
initPasswordRules();
