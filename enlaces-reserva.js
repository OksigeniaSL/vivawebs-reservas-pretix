/* VivaWebs: links straight to a session of the bookings (pretix), for the business's own website.
 *
 * Mark a link and keep a sensible href (the agenda) as the fallback:
 *   <a href="/reservas/ejemplo-academia/clases/" data-reserva="prueba" data-grupo="Inglés B1 · Intermedio"
 *      data-dia="0" data-hora="19:00">…</a>                 → the next session of that group (that weekday, that hour)
 *   <a href="/reservas/ejemplo-academia/matriculas/" data-reserva="matricula"
 *      data-grupo="Inglés B1 · Intermedio">…</a>             → that group's enrolment for its next term
 *   data-grupo is the start of the name in the bookings («Intensivo de inglés B1» for the summer course);
 *   data-dia 0 = Monday … 6 = Sunday (optional); data-hora «HH:MM» (optional).
 *
 * Load it with defer and the organizer's base: <script src="enlaces-reserva.js" data-base="/reservas/ejemplo-academia/" defer>.
 * It reads pretix's public widget data (same domain). If anything fails, the links keep their href. */
(function () {
    'use strict';
    var script = document.currentScript;
    var base = (script && script.getAttribute('data-base')) || '/reservas/';
    if (!window.fetch) {
        return;
    }

    function isoWeek(d) {
        var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
        var day = t.getUTCDay() || 7;
        t.setUTCDate(t.getUTCDate() + 4 - day);
        var y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
        var week = Math.ceil(((t - y0) / 86400000 + 1) / 7);
        return t.getUTCFullYear() + '-W' + (week < 10 ? '0' : '') + week;
    }

    function getJSON(url) {
        return fetch(url, {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .catch(function () { return null; });
    }

    function starts(name, prefix) {
        return String(name || '').toLowerCase().indexOf(String(prefix || '').toLowerCase()) === 0;
    }

    var trials = Array.prototype.slice.call(document.querySelectorAll('a[data-reserva="prueba"][data-grupo]'));
    var enrolments = Array.prototype.slice.call(document.querySelectorAll('a[data-reserva="matricula"][data-grupo]'));

    if (trials.length) {
        // This week and the next two: enough for any weekly group.
        var now = new Date();
        var weeks = [0, 7, 14].map(function (k) { return isoWeek(new Date(now.getTime() + k * 86400000)); });
        Promise.all(weeks.map(function (w) {
            return getJSON(base + 'clases/widget/product_list?style=week&date=' + w);
        })).then(function (answers) {
            var sessions = [];
            answers.forEach(function (r) {
                ((r && r.days) || []).forEach(function (day) {
                    (day && day.events || []).forEach(function (e) {
                        var start = new Date(day.date + 'T' + String(e.time || '00:00').slice(0, 5) + ':00');
                        if (start > now && e.subevent && !(e.availability && e.availability.reason === 'reserved')) {
                            sessions.push({name: e.name, start: start, weekday: (start.getDay() + 6) % 7,
                                hour: String(e.time || '').slice(0, 5), id: e.subevent});
                        }
                    });
                });
            });
            sessions.sort(function (a, b) { return a.start - b.start; });
            trials.forEach(function (a) {
                var day = a.getAttribute('data-dia'), hour = a.getAttribute('data-hora');
                var s = sessions.filter(function (x) {
                    return starts(x.name, a.getAttribute('data-grupo')) &&
                        (day === null || String(x.weekday) === day) && (!hour || x.hour === hour);
                })[0];
                if (s) {
                    a.setAttribute('href', base + 'clases/' + s.id + '/');
                }
            });
        });
    }

    if (enrolments.length) {
        getJSON(base + 'matriculas/widget/product_list?style=list').then(function (r) {
            var list = (r && r.events) || [];
            enrolments.forEach(function (a) {
                var e = list.filter(function (x) { return x.subevent && starts(x.name, a.getAttribute('data-grupo')); })[0];
                if (e) {
                    a.setAttribute('href', base + 'matriculas/' + e.subevent + '/');
                }
            });
        });
    }
}());
