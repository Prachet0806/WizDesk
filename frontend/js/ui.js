/* Keyboard access and focus lifecycle for existing dashboard dialogs. */
(() => {
  'use strict';
  const open = new Map();
  let counter = 0;
  const visible = element => element.isConnected && getComputedStyle(element).display !== 'none' && element.getClientRects().length;
  const focusable = dialog => [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')].filter(el => !el.disabled && el.tabIndex >= 0 && visible(el));
  function sync() {
    document.querySelectorAll('.modal').forEach(modal => {
      if (visible(modal) && !open.has(modal)) {
        open.set(modal, document.activeElement);
        modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true');
        modal.tabIndex = -1;
        const heading = modal.querySelector('h2, h3, .modal-title');
        if (heading) {
          heading.id ||= `dialog-heading-${++counter}`;
          modal.setAttribute('aria-labelledby', heading.id);
        } else {modal.setAttribute('aria-label', 'Dialog');}
        modal.querySelectorAll('.close-modal, .modal-close, .close').forEach(el => {
          el.setAttribute('aria-label', 'Close dialog');
          if (el.tagName !== 'BUTTON') {
            el.setAttribute('role', 'button'); el.tabIndex = 0;
            el.onkeydown = event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); el.click();}};
          }
        });
        (focusable(modal)[0] || modal).focus();
      }
    });
    for (const [modal, previous] of open) {
      if (!visible(modal)) {open.delete(modal); if (previous?.isConnected) previous.focus();}
    }
  }
  document.addEventListener('DOMContentLoaded', () => {
    new MutationObserver(sync).observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ['style', 'class']});
    sync();
  });
  document.addEventListener('keydown', event => {
    const modal = [...open.keys()].at(-1);
    if (!modal) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      const close = modal.querySelector('.close-modal, .modal-close, .close, [data-dialog-close]');
      if (close) close.click(); else modal.style.display = 'none';
      sync();
    } else if (event.key === 'Tab') {
      const items = focusable(modal);
      const first = items[0] || modal, last = items.at(-1) || modal;
      if (!items.length || (event.shiftKey && document.activeElement === first)) {event.preventDefault(); last.focus();}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
    }
  });
})();
