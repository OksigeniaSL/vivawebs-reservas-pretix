/* VivaWebs: the skin of the booking pages, the two things CSS cannot do (Jujol, 8 November 2026).
 * 1. A link back to the business's website, in the top band: the booking lives under /reservas/ of its own domain,
 *    so its website is always «/». The name comes from the page head (the event or organizer name).
 * 2. The colour of each kind of session: vw/marca.css may list name prefixes and colours in --vw-tipos
 *    ("Reformer:#C8372F|Yoga:#D4A20C"); each session of the calendar and each product whose name starts so gets
 *    --tipo, which the stylesheet draws on its side. Text is never replaced: the colour only adds.
 * 3. The week: it changes when it is chosen, and its name is short (see below).
 * 4. On a phone, the week opens at the first day with a free place.
 * Static of the pretix_vivawebs plugin, loaded with defer. Without it, the page is the same minus these two. */
(function () {
    'use strict';

    // 3. The week changes as soon as it is chosen (its button goes, see the stylesheet), and its name says only the
    //    days: «9 al 15 de noviembre», under the word «Semana», so it fits on a phone (Jujol, 9 November 2026).
    document.documentElement.classList.add('vw-js');
    var week = document.querySelector('#monthselform select');
    if (week) {
        Array.prototype.forEach.call(week.options, function (o) {
            o.textContent = o.textContent.replace(/^\s*Semana del\s+/i, '').trim();
        });
        week.addEventListener('change', function () {
            week.form.submit();
        });
    }

    // 4. On a phone the week opens at the first day with a free place: the days before it, already gone or full, fold
    //    to their name, so the first thing under the week is something to book.
    //    pretix folds the days on a phone itself when the page is ready, leaving today open: this goes after it.
    var fold = function () {
        if (!window.matchMedia || !window.matchMedia('(max-width: 767px)').matches) {
            return;
        }
        var days = document.querySelectorAll('.week-calendar details.weekday');
        var first = null;
        for (var d = 0; d < days.length; d++) {
            if (!first && days[d].querySelector('a.event.available')) {
                first = days[d];
            }
            var on = days[d] === first;
            days[d].open = on;
            days[d].classList.toggle('details-open', on);
        }
        // In that day, the sessions before the first free one (closed, gone or full) fold into one line that shows them.
        if (!first || first.querySelector('.vw-anteriores')) {
            return;
        }
        var items = Array.prototype.slice.call(first.querySelectorAll('ul.events > li'));
        var before = [];
        for (var k = 0; k < items.length && !items[k].querySelector('a.event.available'); k++) {
            before.push(items[k]);
        }
        if (before.length < 2) {
            return;
        }
        var lang = (document.documentElement.lang || 'es').slice(0, 2);
        var say = {es: [' anteriores, cerradas', 'Verlas'], en: [' earlier, closed', 'Show'], de: [' frühere, geschlossen', 'Zeigen']};
        var words = say[lang] || say.es;
        var line = document.createElement('li');
        line.className = 'vw-anteriores';
        var text = document.createElement('span');
        text.textContent = before.length + words[0];
        var show = document.createElement('button');
        show.type = 'button';
        show.textContent = words[1];
        show.addEventListener('click', function () {
            before.forEach(function (li) {
                li.hidden = false;
            });
            line.remove();
        });
        line.appendChild(text);
        line.appendChild(show);
        before.forEach(function (li) {
            li.hidden = true;
        });
        before[0].parentNode.insertBefore(line, before[0]);
    };
    if (document.readyState === 'complete') {
        fold();
    } else {
        window.addEventListener('load', function () {
            window.setTimeout(fold, 0);
        });
    }

    var head = document.querySelector('.page-header h1');
    var links = document.querySelector('body > header .page-header-links');
    if (links && !links.querySelector('.vw-volver')) {
        var name = head ? head.textContent.replace(/\s+/g, ' ').trim() : '';
        var back = document.createElement('a');
        back.className = 'vw-volver';
        back.href = '/';
        back.textContent = name || document.location.hostname;
        links.insertBefore(back, links.firstChild);
    }

    var raw = window.getComputedStyle(document.documentElement).getPropertyValue('--vw-tipos').trim();
    raw = raw.replace(/^["']|["']$/g, '');
    if (!raw) {
        return;
    }
    var kinds = raw.split('|').map(function (pair) {
        var i = pair.lastIndexOf(':');
        return {name: pair.slice(0, i).trim().toLowerCase(), colour: pair.slice(i + 1).trim()};
    }).filter(function (k) {
        return k.name && /^#[0-9a-f]{3,8}$/i.test(k.colour);
    }).sort(function (a, b) {
        return b.name.length - a.name.length;      // the longest prefix first: «Pilates suelo» before «Pilates»
    });
    // By the start of its name; if none, by a part after «·» («Clase de prueba · Reformer» is a Reformer): one kind, one
    // colour, whatever the session is called.
    var kindOf = function (text) {
        var t = (text || '').replace(/\s+/g, ' ').trim().toLowerCase();
        var parts = [t].concat(t.split('·').slice(1).map(function (x) { return x.trim(); }));
        for (var p = 0; p < parts.length; p++) {
            for (var i = 0; i < kinds.length; i++) {
                if (parts[p].indexOf(kinds[i].name) === 0) {
                    return kinds[i];
                }
            }
        }
        return null;
    };
    var paint = function (el, text) {
        var k = kindOf(text);
        if (k) {
            el.style.setProperty('--tipo', k.colour);
        }
    };
    Array.prototype.forEach.call(document.querySelectorAll('.event'), function (ev) {
        var n = ev.querySelector('.event-name');
        paint(ev, n ? n.textContent : ev.textContent);
    });
    // What each colour means, in one line above the calendar (Kimi, fifth round): only the kinds that are in the week,
    // with their name as the business writes it. A business of courts (one kind per court) does not need it.
    var calendar = document.querySelector('.week-calendar, .table-calendar, .day-calendar');
    if (calendar && !document.querySelector('.vw-leyenda') && !document.documentElement.classList.contains('vw-forma-pistas')) {
        var seen = [];
        Array.prototype.forEach.call(calendar.querySelectorAll('.event-name'), function (n) {
            var k = kindOf(n.textContent);
            if (k && seen.indexOf(k) < 0) {
                seen.push(k);
            }
        });
        if (seen.length > 1) {
            var legend = document.createElement('ul');
            legend.className = 'vw-leyenda';
            legend.setAttribute('aria-label', 'Tipos de clase');
            raw.split('|').forEach(function (pair) {
                var i = pair.lastIndexOf(':');
                var name = pair.slice(0, i).trim();
                var kind = seen.filter(function (k) { return k.name === name.toLowerCase(); })[0];
                if (kind) {
                    var li = document.createElement('li');
                    li.style.setProperty('--tipo', kind.colour);
                    li.textContent = name;
                    legend.appendChild(li);
                }
            });
            var nav = document.querySelector('.calendar-nav');
            (nav || calendar).parentNode.insertBefore(legend, nav ? nav.nextSibling : calendar);
        }
    }
    Array.prototype.forEach.call(document.querySelectorAll('.product-row'), function (row) {
        var n = row.querySelector('h4, .h4');
        paint(row, n ? n.textContent : '');
    });
}());

/* Each business, its own (Jujol, 10 November 2026; Kimi, third round: «Vértebra and Volea share a skeleton to the
 * millimetre»). From vw/marca.css, like --vw-tipos, all optional:
 * - --vw-forma: "pistas", for the slots of a court or a room: each one a card touched whole, with its hour, its price
 *   and its state, and no button in each one (the strong colour is kept for confirming);
 * - --vw-cabecera-foto, --vw-cabecera-foto-alt and --vw-cabecera-lema: a photo of the place and a line of its own,
 *   beside its name, at the top;
 * - --vw-precio-sesion: what a session costs, said on each free one («desde 18 €»);
 * - --vw-dia-vacio: what a day without sessions says («Cerrado»); without it, «Sin sesiones».
 * And for every business: the demo account, folded behind «¿Cómo pruebo los bonos?», and a day whose sessions are all
 * closed, folded into one line that shows them. */
(function () {
    'use strict';
    var css = window.getComputedStyle(document.documentElement);
    var prop = function (name) {
        return css.getPropertyValue(name).trim().replace(/^["']|["']$/g, '');
    };
    var lang = (document.documentElement.lang || 'es').slice(0, 2);
    var WORDS = {
        es: {test: '¿Cómo pruebo los bonos?', empty: 'Sin sesiones', closed: [' cerrada', ' cerradas'], show: ['Verla', 'Verlas']},
        en: {test: 'How do I try the passes?', empty: 'No sessions', closed: [' closed', ' closed'], show: ['Show', 'Show']},
        de: {test: 'Wie teste ich die Karten?', empty: 'Keine Termine', closed: [' geschlossen', ' geschlossen'],
            show: ['Zeigen', 'Zeigen']}
    };
    var T = WORDS[lang] || WORDS.es;
    var el = function (tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) {
            e.className = cls;
        }
        if (text) {
            e.textContent = text;
        }
        return e;
    };

    var shape = prop('--vw-forma');
    if (/^[a-z-]+$/.test(shape)) {
        document.documentElement.classList.add('vw-forma-' + shape);
    }

    // The head: the name, a line of the business's own and the photo of the place.
    var header = document.querySelector('main .page-header');
    var photo = prop('--vw-cabecera-foto');
    var motto = prop('--vw-cabecera-lema');
    if (header && (photo || motto) && !header.classList.contains('vw-cabecera-propia')) {
        header.classList.add('vw-cabecera-propia');
        var words = el('div', 'vw-cabecera-texto');
        var title = header.querySelector('.pull-left') || header.querySelector('h1');
        if (title) {
            header.insertBefore(words, title);
            words.appendChild(title);
        }
        if (motto) {
            words.appendChild(el('p', 'vw-lema', motto));
        }
        if (/^\/[A-Za-z0-9_./-]+\.(webp|jpg|jpeg|png)$/.test(photo)) {
            var fig = el('figure', 'vw-cabecera-foto');
            var img = el('img');
            img.src = photo;
            img.alt = prop('--vw-cabecera-foto-alt');
            img.decoding = 'async';
            fig.appendChild(img);
            header.appendChild(fig);
        }
    }

    // The demo account: folded, under the head (or where it was), so the first screen sells the business, not the demo.
    var test = document.querySelector('.vw-prueba');
    if (test && !test.closest('details')) {
        var fold = el('details', 'vw-prueba-plegada');
        fold.appendChild(el('summary', '', T.test));
        var place = header && header.querySelector('.vw-cabecera-texto');
        if (place) {
            place.appendChild(fold);
        } else {
            var intro = document.querySelector('main .alert-warning + div') || header;
            if (intro) {
                intro.parentNode.insertBefore(fold, intro.nextSibling);
            } else {
                test.parentNode.insertBefore(fold, test);
            }
        }
        fold.appendChild(test);
    }

    // Each day: what an empty one says, and the sessions of a day that are all closed, in one line.
    var empty = prop('--vw-dia-vacio') || T.empty;
    Array.prototype.forEach.call(document.querySelectorAll('.week-calendar details.weekday'), function (day) {
        var list = day.querySelector('ul.events');
        if (!list || list.querySelector('.vw-dia-vacio, .vw-cerradas')) {
            return;
        }
        var items = Array.prototype.slice.call(list.children);
        if (!items.length) {
            list.appendChild(el('li', 'vw-dia-vacio', empty));
            return;
        }
        var closed = items.filter(function (li) {
            return li.querySelector('a.event.over');
        });
        if (closed.length < 2 || closed.length !== items.length) {
            return;
        }
        var one = closed.length === 1 ? 0 : 1;
        var line = el('li', 'vw-cerradas');
        line.appendChild(el('span', '', closed.length + T.closed[one]));
        var show = el('button', '', T.show[one]);
        show.type = 'button';
        show.addEventListener('click', function () {
            closed.forEach(function (li) {
                li.hidden = false;
            });
            line.remove();
        });
        line.appendChild(show);
        closed.forEach(function (li) {
            li.hidden = true;
        });
        list.insertBefore(line, list.firstChild);
    });

    // What a session costs, on each free one.
    var price = prop('--vw-precio-sesion');
    if (price) {
        Array.prototype.forEach.call(document.querySelectorAll('a.event.available'), function (ev) {
            if (!ev.querySelector('.vw-precio')) {
                var status = ev.querySelector('.event-status');
                ev.insertBefore(el('span', 'vw-precio', price), status);
            }
        });
    }
}());

/* What is left in each free session (Kimi, fifth round; the data, from pretix_vivawebs, 10 November 2026): on a business
 * of courts or rooms, how many are free at that hour («4 pistas libres»); on classes, the places left («quedan 2»). It
 * comes from /reservas/vw-semana for the week on screen, and is written when it arrives: the calendar never waits. */
(function () {
    'use strict';
    var events = document.querySelectorAll('.week-calendar a.event.available, .day-calendar a.event.available, .table-calendar a.event.available');
    if (!events.length || !window.fetch) {
        return;
    }
    var courts = document.documentElement.classList.contains('vw-forma-pistas');
    var lang = (document.documentElement.lang || 'es').slice(0, 2);
    // What is free, by its name in the business's marca.css: --vw-libre-nombre: "pista|pistas" (one|several).
    var noun = (window.getComputedStyle(document.documentElement).getPropertyValue('--vw-libre-nombre') || '').trim()
        .replace(/^["']|["']$/g, '').split('|');
    var named = function (n) {
        var word = n === 1 ? noun[0] : (noun[1] || noun[0]);
        return word ? n + ' ' + word + ' ' : n + ' ';
    };
    var WORDS = {
        es: {free: function (n) { return named(n) + (n === 1 ? 'libre' : 'libres'); },
            left: function (n) { return n === 1 ? 'queda 1' : 'quedan ' + n; }},
        en: {free: function (n) { return n + ' free'; }, left: function (n) { return n + ' left'; }},
        de: {free: function (n) { return n + ' frei'; }, left: function (n) { return 'noch ' + n; }}
    };
    var T = WORDS[lang] || WORDS.es;
    var week = (window.location.search.match(/[?&]date=(\d{4}-W\d{2})/) || [])[1];
    var base = (document.querySelector('a.event').getAttribute('href').match(/^(.*?\/reservas)\//) || [])[1] || '/reservas';
    fetch(base + '/vw-semana' + (week ? '?semana=' + week : ''), {credentials: 'same-origin', headers: {Accept: 'application/json'}})
        .then(function (r) {
            if (!r.ok) {
                throw new Error(r.status);
            }
            return r.json();
        })
        .then(function (data) {
            var sessions = (data && data.sessions) || (data && data.sesiones) || {};
            Array.prototype.forEach.call(events, function (ev) {
                var id = ((ev.getAttribute('href') || '').match(/\/(\d+)\/?(?:\?|$)/) || [])[1];
                var s = id && sessions[id];
                if (!s || ev.querySelector('.vw-libres')) {
                    return;
                }
                var n = courts ? s.libres : s.plazas;
                if (typeof n !== 'number' || n < 1) {
                    return;
                }
                var tag = document.createElement('span');
                tag.className = 'vw-libres' + (n <= 2 ? ' vw-pocas' : '');
                tag.textContent = courts ? T.free(n) : T.left(n);
                var status = ev.querySelector('.event-status');
                ev.insertBefore(tag, status);
            });
        })
        .catch(function () { /* without the data, the calendar as it is */ });
}());
