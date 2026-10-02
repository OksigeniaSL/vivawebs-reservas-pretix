"""Lector mínimo de .po (msgctxt, msgid, msgid_plural, msgstr[n], referencias)."""
import re
def _s(line):
    return eval(line[line.index('"'):]) if '"' in line else ""
def leer(path):
    entradas, e, campo = [], None, None
    for raw in open(path, encoding="utf-8"):
        l = raw.rstrip("\n")
        if not l.strip():
            if e: entradas.append(e); e = None
            continue
        if e is None: e = {"refs": [], "flags": "", "msgctxt": None, "msgid": "", "msgid_plural": None, "msgstr": {}, "obsoleto": False}
        if l.startswith("#~"): e["obsoleto"] = True; continue
        if l.startswith("#:"): e["refs"] += l[2:].split(); continue
        if l.startswith("#,"): e["flags"] = l[2:].strip(); continue
        if l.startswith("#"): continue
        m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(".*")$', l)
        if m:
            k, n, v = m.group(1), m.group(2), eval(m.group(3))
            if k.startswith("msgstr"): campo = ("msgstr", int(n) if n else 0); e["msgstr"][campo[1]] = v
            else: campo = (k, None); e[k] = v
        elif l.startswith('"') and campo:
            if campo[0] == "msgstr": e["msgstr"][campo[1]] += eval(l)
            else: e[campo[0]] = (e[campo[0]] or "") + eval(l)
    if e: entradas.append(e)
    return [x for x in entradas if x["msgid"] and not x["obsoleto"]]
