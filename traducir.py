"""Reescribe la traducción española de pretix para el servicio de reservas de VivaWebs: español de
España, tuteo al cliente, panel neutro y vocabulario de reservas (no de venta de entradas).

Se ejecuta en el contenedor del builder (tiene la biblioteca y la clave de la IA):
    docker cp textos.json builder-api:/tmp/pretix-es/textos.json
    docker exec -w /app -e PYTHONPATH=/app builder-api python /tmp/pretix-es/traducir.py
Entrada  /tmp/pretix-es/textos.json: [{"id", "zona", "en", "en_pl", "es": [formas]}]
Salida   /tmp/pretix-es/resultado.json: {"id": [formas]} solo de los textos que pasan la validación.
"""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from anthropic import Anthropic
from app.config import get_settings

s = get_settings()
client = Anthropic(api_key=s.anthropic_api_key)
MODELO = s.claude_model_builder
textos = json.load(open("/tmp/pretix-es/textos.json"))

SISTEMA = """Reescribes en español de España los textos de pretix, un programa de venta de entradas que VivaWebs usa como SISTEMA DE RESERVAS para pequeños negocios: clases y talleres (yoga, cerámica, visitas) y citas en salas o cabinas (masajes, sauna, pistas). Nadie compra entradas: el cliente RESERVA.
Recibes un JSON {"id": {"z": zona, "en": original inglés, "en_pl": plural inglés o null, "es": [traducción actual: forma singular y, si hay plural, forma plural]}}.
Devuelve SOLO un JSON {"id": ["singular", "plural si lo había"]} con el MISMO número de formas que "es".
Reglas:
- Español de España, natural y breve. Zona "c" (lo ve el cliente): tutéale (tú, tu reserva, recibirás). Zona "p" (panel del negocio) y "b" (general): estilo neutro e impersonal, sin «usted»; si hace falta dirigirse al dueño, tutéale.
- Mayúscula solo al principio de la frase y en nombres propios (Lista de espera, no Lista De Espera).
- Vocabulario OBLIGATORIO: order → reserva (order code → código de reserva; orders → reservas); ticket, admission, entrada → plaza (o «reserva» si suena mejor); product, item → servicio; quota → cupo; event (la página completa) → agenda; date, subevent (una fecha concreta) → sesión; shop, ticket shop → página de reservas; cart, basket → tu selección; add to cart → añadir; checkout, proceed to checkout → continuar con la reserva; place (binding) order → confirmar la reserva; buy, purchase, sell → reservar; sold out → completo; on sale, available for sale → abierto a reservas; buyer, customer → cliente; attendee → participante; organizer → negocio; voucher → código; check-in → registro de llegada.
- Nunca uses «entrada», «pedido», «carrito», «cesta», «tienda», «comprar», «compra» ni «venta» salvo en el nombre «pretix».
- Conserva EXACTAMENTE, sin traducir ni mover dentro del texto de forma que cambie su sentido: variables %(nombre)s, %(n)d, %s, %d, {nombre}, {0}; etiquetas HTML, atributos y entidades (&amp;); URLs; marcas de Markdown (**, `, [texto](url)); saltos de línea \\n.
- No añadas explicaciones ni comillas. Si un texto es solo un código o una variable, devuélvelo igual."""

TOK = re.compile(r"%\([A-Za-z0-9_]+\)[sdif]|%[sdif]|\{[^{}]*\}|<[^>]+>|&[a-z#0-9]+;|https?://\S+")
def firma(t):
    return sorted(TOK.findall(t))

def valido(orig_es, nuevas):
    if not isinstance(nuevas, list) or len(nuevas) != len(orig_es):
        return False
    for a, b in zip(orig_es, nuevas):
        if not isinstance(b, str) or (a.strip() and not b.strip()) or firma(a) != firma(b):
            return False
        if a.count("\n") != b.count("\n"):
            return False
    return True

def lote(items, intento=0):
    entrada = {t["id"]: {"z": t["zona"], "en": t["en"], "en_pl": t["en_pl"], "es": t["es"]} for t in items}
    try:
        r = client.messages.create(model=MODELO, max_tokens=16000, system=SISTEMA,
                                   messages=[{"role": "user", "content": json.dumps(entrada, ensure_ascii=False)}])
        txt = "".join(b.text for b in r.content if b.type == "text").strip()
        out = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        uso = (r.usage.input_tokens, r.usage.output_tokens)
    except Exception as e:
        print("  fallo de lote:", str(e)[:120], flush=True)
        out, uso = {}, (0, 0)
    buenos, malos = {}, []
    for t in items:
        n = out.get(t["id"])
        if valido(t["es"], n):
            buenos[t["id"]] = n
        else:
            malos.append(t)
    if malos and intento < 2:
        time.sleep(3)
        extra, u2 = lote(malos, intento + 1)
        buenos.update(extra)
        uso = (uso[0] + u2[0], uso[1] + u2[1])
    return buenos, uso

lotes = [textos[k:k + 60] for k in range(0, len(textos), 60)]
res, tin, tout = {}, 0, 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for buenos, (a, b) in ex.map(lote, lotes):
        res.update(buenos); tin += a; tout += b
        print(f"  {len(res)}/{len(textos)}", flush=True)
json.dump(res, open("/tmp/pretix-es/resultado.json", "w"), ensure_ascii=False)
print(f"reescritos {len(res)}/{len(textos)} | tokens entrada {tin} salida {tout} | coste aprox ${tin / 1e6 * 3 + tout / 1e6 * 15:.2f}")
