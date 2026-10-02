/* VivaWebs: comprobación anti-robots de Cloudflare (Turnstile) al reservar. No se ve salvo que
   Cloudflare pida un clic (nunca puzles). Su token va en el campo que indica data-campo. Si se pulsa
   «Continuar» antes de que llegue el token (tarda un par de segundos), el formulario espera hasta 10 s. */
(function () {
  "use strict";
  function iniciar() {
    var caja = document.querySelector(".vw-captcha");
    if (!caja) return;
    if (!window.turnstile) { setTimeout(iniciar, 300); return; }
    var campo = caja.getAttribute("data-campo"), token = "";
    window.turnstile.render(caja, {
      sitekey: caja.getAttribute("data-sitekey"), language: "es", appearance: "interaction-only",
      "response-field-name": campo,
      callback: function (t) { token = t; },
      "expired-callback": function () { token = ""; },
      "error-callback": function () { token = ""; }
    });
    var form = caja.closest("form"), esperando = false, pasar = false;
    if (!form) return;
    form.addEventListener("submit", function (ev) {
      if (pasar || token) return;
      ev.preventDefault();
      if (esperando) return;
      esperando = true;
      var n = 0;
      (function mirar() {
        if (token || ++n > 40) { esperando = false; pasar = true; form.requestSubmit ? form.requestSubmit() : form.submit(); }
        else setTimeout(mirar, 250);
      })();
    }, true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
