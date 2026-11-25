// Applied before first paint so the page never flashes the wrong theme.
(function () {
  var theme = 'system';
  try {
    theme = localStorage.getItem('theme') || 'system';
  } catch (_) {
    theme = 'system';
  }
  var dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
})();
