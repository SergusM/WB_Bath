// Мелкие помощники интерфейса: создание элементов, тосты, подтверждение, степпер.
window.UI = (function () {
  "use strict";

  // h("div", {class: "card", onclick: fn}, "текст", childEl, [ещё, дети])
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    append(el, kids);
    return el;
  }

  function append(el, kids) {
    for (const kid of kids) {
      if (kid === null || kid === undefined || kid === false) continue;
      if (Array.isArray(kid)) append(el, kid);
      else el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
  }

  function setText(el, text) {
    if (el.textContent !== text) el.textContent = text;
  }

  function toast(text, kind) {
    const box = document.getElementById("toasts");
    const el = h("div", {class: "toast" + (kind ? " " + kind : "")}, text);
    box.appendChild(el);
    setTimeout(() => el.remove(), kind === "error" ? 6000 : 3000);
  }

  // Диалог подтверждения → Promise<boolean>
  function confirm(text, okLabel) {
    const dlg = document.getElementById("dialog");
    const ok = document.getElementById("dialog-ok");
    const cancel = document.getElementById("dialog-cancel");
    document.getElementById("dialog-text").textContent = text;
    ok.textContent = okLabel || "Да";
    dlg.hidden = false;
    ok.focus();
    return new Promise((resolve) => {
      function done(result) {
        dlg.hidden = true;
        ok.removeEventListener("click", yes);
        cancel.removeEventListener("click", no);
        dlg.removeEventListener("click", outside);
        resolve(result);
      }
      function yes() { done(true); }
      function no() { done(false); }
      function outside(e) { if (e.target === dlg) done(false); }
      ok.addEventListener("click", yes);
      cancel.addEventListener("click", no);
      dlg.addEventListener("click", outside);
    });
  }

  // Кнопка «занята», пока команда ждёт ответа; ошибка — тостом
  function act(el, promise) {
    if (el) el.classList.add("busy");
    const done = () => { if (el) el.classList.remove("busy"); };
    return promise.then(
      (r) => { done(); return r; },
      (e) => { done(); toast(e.message, "error"); throw e; });
  }

  // Степпер −/+ с автоповтором при удержании. Значение отправляется через
  // commitDelay после последнего нажатия. Пока правка не подтверждена
  // контроллером, значения из state её не перетирают.
  function stepper(opts) {
    const o = Object.assign({min: 0, max: 100, step: 1, commitDelay: 600}, opts);
    let value = o.value || 0;
    let pending = false;
    let committedAt = 0;
    let timer = null;
    let repeat = null;

    const out = h("output", {}, String(value));
    const minus = h("button", {type: "button", "aria-label": "Меньше"}, "−");
    const plus = h("button", {type: "button", "aria-label": "Больше"}, "+");
    const el = h("span", {class: "stepper ctl"}, minus, out, plus);

    function bump(dir) {
      const next = Math.min(o.max, Math.max(o.min, value + dir * o.step));
      if (next === value) return;
      value = next;
      pending = true;
      committedAt = 0;
      render();
      clearTimeout(timer);
      timer = setTimeout(commit, o.commitDelay);
    }

    function commit() {
      committedAt = Date.now();
      Promise.resolve(o.onCommit(value)).catch(() => {
        pending = false;
        render();
      });
    }

    function hold(btn, dir) {
      btn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        bump(dir);
        let delay = 400;
        const tick = () => { bump(dir); delay = Math.max(60, delay * 0.75); repeat = setTimeout(tick, delay); };
        repeat = setTimeout(tick, delay);
      });
      for (const ev of ["pointerup", "pointerleave", "pointercancel"]) {
        btn.addEventListener(ev, () => clearTimeout(repeat));
      }
    }
    hold(minus, -1);
    hold(plus, 1);

    function render() {
      setText(out, String(value));
      el.classList.toggle("pending", pending);
    }

    return {
      el,
      // Значение из state: принимаем, если своих неподтверждённых правок нет,
      // контроллер уже применил их или подтверждение не пришло за 3 с
      set(v) {
        if (pending) {
          const stale = committedAt && Date.now() - committedAt > 3000;
          if (v !== value && !stale) return;
          pending = false;
        }
        value = v;
        render();
      },
    };
  }

  function plural(n, one, few, many) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  function mmss(s) {
    if (s === null || s === undefined) return "—";
    s = Math.max(0, Math.round(s));
    const m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  }

  function temp(v) {
    return v === null || v === undefined ? "—" : String(Math.round(v));
  }

  return {h, setText, toast, confirm, act, stepper, plural, mmss, temp};
})();
