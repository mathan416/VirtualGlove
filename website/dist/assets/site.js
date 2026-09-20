(() => {
  const menu = document.querySelector('[data-menu]');
  const navigation = document.querySelector('[data-navigation]');
  if (menu && navigation) {
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(open));
      navigation.classList.toggle('open', open);
    });
  }
  document.querySelectorAll('[data-copy-target]').forEach(button => {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(target.textContent);
        button.textContent = 'Copied';
      } catch (_) {
        button.textContent = 'Select the command';
      }
      window.setTimeout(() => { button.textContent = original; }, 1800);
    });
  });
})();
