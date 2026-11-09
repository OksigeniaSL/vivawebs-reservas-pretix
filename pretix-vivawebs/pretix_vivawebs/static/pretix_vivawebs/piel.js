/* VivaWebs: the skin of the booking pages, the two things CSS cannot do (Jujol, 8 November 2026).
 * 1. A link back to the business's website, in the top band: the booking lives under /reservas/ of its own domain,
 *    so its website is always «/». The name comes from the page head (the event or organizer name).
 * 2. The colour of each kind of session: vw/marca.css may list name prefixes and colours in --vw-tipos
 *    ("Reformer:#C8372F|Yoga:#D4A20C"); each session of the calendar and each product whose name starts so gets
 *    --tipo, which the stylesheet draws on its side. Text is never replaced: the colour only adds.
 * Static of the pretix_vivawebs plugin, loaded with defer. Without it, the page is the same minus these two. */
(function () {
    'use strict';

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
    var paint = function (el, text) {
        var t = (text || '').replace(/\s+/g, ' ').trim().toLowerCase();
        for (var i = 0; i < kinds.length; i++) {
            if (t.indexOf(kinds[i].name) === 0) {
                el.style.setProperty('--tipo', kinds[i].colour);
                return;
            }
        }
    };
    Array.prototype.forEach.call(document.querySelectorAll('.event'), function (ev) {
        var n = ev.querySelector('.event-name');
        paint(ev, n ? n.textContent : ev.textContent);
    });
    Array.prototype.forEach.call(document.querySelectorAll('.product-row'), function (row) {
        var n = row.querySelector('h4, .h4');
        paint(row, n ? n.textContent : '');
    });
}());
