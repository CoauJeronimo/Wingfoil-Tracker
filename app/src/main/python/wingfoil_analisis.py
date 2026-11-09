#!/usr/bin/env python3
"""Análisis WingFoil Completo — Sensor Logger o Wingfoil Tracker (Android) -> KML + Excel.
Uso:
  python3 wingfoil_analisis.py --location Location.csv --metadata Metadata.csv --wind 169 --fecha 25-10-2026 [--sections 3] [--outdir out]
                               [--exclude 14:57:18-15:09:39 ...] [--max-acc 10] [--gap 5]
  --location también acepta el .zip de Wingfoil Tracker (se leen Location.csv y Metadata.csv de adentro; track.gpx no se usa).
--wind: grados de DONDE VIENE el viento (obligatorio).
--metadata: Metadata.csv. Da el 'recording epoch time' y el origen (Sensor Logger / Wingfoil Tracker).
  Sin --metadata hay que pasar --epoch-ms (columna 'recording epoch time').
--exclude: tramos a retirar (hora local HH:MM:SS-HH:MM:SS, o seconds_elapsed a-b), p.ej. salidas del agua.
  El track queda partido en segmentos: no se une el hueco, ni se cuenta su tiempo o distancia.
--max-acc: precisión horizontal máxima en m (por defecto 10 para Wingfoil Tracker, 20 para Sensor Logger).
--gap: segundos sin puntos válidos que cortan el track (por defecto 5 para Wingfoil Tracker; 0 = desactivado,
  que es el defecto para Sensor Logger). El corte se trata igual que un --exclude: no suma tiempo, distancia ni planeo.
Requiere: python3 + openpyxl.
"""
import wf_textos
import csv, math, json, bisect, argparse, os, datetime, io, zipfile, array
from collections import Counter
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

ap = argparse.ArgumentParser()
ap.add_argument('--location', required=True); ap.add_argument('--wind', type=float, required=True)
ap.add_argument('--epoch-ms', type=float); ap.add_argument('--metadata'); ap.add_argument('--fecha', required=True)
ap.add_argument('--max-acc', type=float); ap.add_argument('--gap', type=float)
ap.add_argument('--sections', type=int, default=3); ap.add_argument('--outdir', default='.')
ap.add_argument('--utc-offset', type=float, default=-3.0)
ap.add_argument('--exclude', nargs='*', default=[])
ap.add_argument('--json', help='opcional: guarda los resultados en JSON (lo usa la app para el PDF)')
ap.add_argument('--salto-min', type=float, default=1.0, help='tiempo mínimo en vuelo (s) para contar un salto (por defecto 1.0)')
ap.add_argument('--nombre', default='', help='opcional: nombre de la sesión')
ap.add_argument('--lugar', default='', help='opcional: lugar de la sesión')
ap.add_argument('--viento-kn', type=float, help='opcional: intensidad del viento (nudos)')
ap.add_argument('--comentario', default='', help='opcional: comentario libre')
ap.add_argument('--salto-h-min', type=float, default=0.5, help='altura mínima estimada (m) para contar un salto (por defecto 0.5)')
ap.add_argument('--disciplina', choices=['wingfoil', 'windsurf'], default='wingfoil',
                help='wingfoil (por defecto) o windsurf: cambia los umbrales de maniobra y lo que se informa (en windsurf no se informa el planeo)')
A = ap.parse_args()
WS = A.disciplina == 'windsurf'
DISC = 'Windsurf' if WS else 'Wingfoil'
V_NAV = 4.0 if WS else 7.0        # velocidad mínima para medir ángulos al viento, rumbos y VMG (navegando / en planeo)
V_ENT_MIN = 4.0 if WS else 6.0    # velocidad mínima de entrada (40 m previos) para contar una maniobra
K = 1.9438444924406            # m/s -> nudos
WIND_FROM = A.wind % 360; DOWNWIND = (WIND_FROM + 180) % 360
UTC = A.utc_offset

# 0) ARCHIVOS Y ORIGEN: Location.csv / Metadata.csv sueltos o dentro del zip de Wingfoil Tracker
def _abrir(path, nombre=None):
    if path.lower().endswith('.zip'):
        z = zipfile.ZipFile(path)
        cands = [x for x in z.namelist() if os.path.basename(x).lower() == nombre.lower()]
        if not cands: return None
        return io.StringIO(z.read(cands[0]).decode('utf-8-sig'))
    return open(path, encoding='utf-8-sig')
loc_f = _abrir(A.location, 'Location.csv')
meta = {}
mf = _abrir(A.metadata) if A.metadata else (_abrir(A.location, 'Metadata.csv') if A.location.lower().endswith('.zip') else None)
if mf:
    rows_ = list(csv.DictReader(mf))
    if rows_: meta = {(k or '').strip().lower(): (v_ or '').strip() for k, v_ in rows_[0].items()}
appv = meta.get('appversion', '')
if 'gpx importado' in appv.lower(): ORIGEN = 'GPX importado'
elif 'wingfoiltracker' in appv.lower().replace(' ', ''): ORIGEN = 'Wingfoil Tracker'
elif meta: ORIGEN = 'Sensor Logger'
else: ORIGEN = 'No identificado (sin Metadata.csv)'
if ORIGEN == 'GPX importado':
    ORIGEN_TXT = 'Sesión importada (GPX)' + (f" - {appv.split(' - ', 1)[1]}" if ' - ' in appv else '') + \
                 (' · velocidad calculada por posición' if 'velocidad-por-posicion' in meta.get('sensors', '') else '')
elif appv: ORIGEN_TXT = f"{ORIGEN} ({appv})"
else: ORIGEN_TXT = ORIGEN
TRACKER = ORIGEN == 'Wingfoil Tracker'
MAXACC = A.max_acc if A.max_acc is not None else (10.0 if TRACKER else 20.0)
GAP = A.gap if A.gap is not None else (5.0 if TRACKER else 0.0)
if A.epoch_ms is not None: EP = A.epoch_ms / 1000.0
elif meta.get('recording epoch time'): EP = float(meta['recording epoch time']) / 1000.0
else: raise SystemExit("Falta el 'recording epoch time': pasar --metadata Metadata.csv o --epoch-ms")
print(f"Origen: {ORIGEN_TXT} | precisión máx {MAXACC:g} m | corte por hueco {'> %g s' % GAP if GAP > 0 else 'desactivado'}")

def hv(a, b, c, d):
    R = 6371000; p1, p2 = math.radians(a), math.radians(c); dp = p2 - p1; dl = math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))
def brg(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c); dl = math.radians(d - b)
    x = math.sin(dl)*math.cos(p2); y = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

# 1) LIMPIEZA GPS: precisión > MAXACC fuera; saltos > 35 nudos fuera. Celdas vacías toleradas.
def _f(r, k):
    x = (r.get(k) or '').strip()
    return float(x) if x else None
raw = []; n_acc = 0
for r in csv.DictReader(loc_f):
    try:
        la = _f(r, 'latitude'); lo = _f(r, 'longitude'); sp = _f(r, 'speed'); t = _f(r, 'seconds_elapsed')
        if t is None and _f(r, 'time') is not None: t = _f(r, 'time')/1e9 - EP
        ac = _f(r, 'horizontalAccuracy')
    except ValueError: continue
    if None in (la, lo, sp, t): continue
    if ac is not None and ac > MAXACC: n_acc += 1; continue
    raw.append((t, la, lo, sp * K))
raw.sort(key=lambda x: x[0])
if ORIGEN == 'GPX importado' and A.gap is None and len(raw) > 2:     # GPX: corte por hueco según su frecuencia de puntos
    _dts = sorted(raw[k+1][0] - raw[k][0] for k in range(len(raw)-1) if raw[k+1][0] > raw[k][0])
    GAP = max(5.0, 3 * _dts[len(_dts)//2]) if _dts else 5.0
    print(f"GPX importado: corte por hueco > {GAP:g} s")
if not raw: raise SystemExit('La sesión no tiene puntos GPS válidos (todos sin posición o con mala precisión).')
print(f"Puntos descartados por precisión (> {MAXACC:g} m): {n_acc}")
def _tsec(x):
    if ':' not in x: return float(x)
    h, m, s_ = (float(q) for q in x.split(':')); loc = h*3600 + m*60 + s_
    d0 = datetime.datetime.fromtimestamp(EP, datetime.timezone.utc) + datetime.timedelta(hours=UTC)
    return loc - (d0.hour*3600 + d0.minute*60 + d0.second + d0.microsecond/1e6)
EXC = []
for e in A.exclude:
    a_, b_ = e.split('-'); EXC.append((_tsec(a_), _tsec(b_)))
if EXC:
    nb = len(raw); raw = [x for x in raw if not any(a_ <= x[0] <= b_ for a_, b_ in EXC)]
    print(f"Tramos excluidos: {EXC} -> {nb-len(raw)} puntos retirados")
if not raw: raise SystemExit('No quedan puntos después de excluir los tramos indicados.')
cl = [raw[0]]
for x in raw[1:]:
    dt = x[0] - cl[-1][0]
    if dt <= 0: continue
    if hv(cl[-1][1], cl[-1][2], x[1], x[2]) / dt * K > 35: continue
    cl.append(x)

# 2) RECORTE: inicio = primer punto >= 4 kn; fin = último punto > 4 kn (se descarta la cola lenta final)
i0 = next((i for i, c in enumerate(cl) if c[3] >= 4), None)
if i0 is None: raise SystemExit('La sesión no tiene navegación: ningún punto llega a 4 nudos.')
i1 = next(i for i in range(len(cl)-1, -1, -1) if cl[i][3] > 4)
cl = cl[i0:i1+1]
if len(cl) < 3: raise SystemExit('La sesión es demasiado corta para analizar.')
n = len(cl); t = [c[0] for c in cl]; lat = [c[1] for c in cl]; lon = [c[2] for c in cl]; v = [c[3] for c in cl]
seg = [0]*n          # segmento: cambia al cruzar un tramo excluido o un corte de señal (> GAP s sin puntos válidos)
corte = {}           # seg que TERMINA en un corte de señal -> duración del hueco (s)
for i in range(1, n):
    exc_ = any(t[i-1] < a_ and t[i] > b_ for a_, b_ in EXC)
    gap_ = (not exc_) and GAP > 0 and t[i]-t[i-1] > GAP
    seg[i] = seg[i-1] + (1 if exc_ or gap_ else 0)
    if gap_: corte[seg[i-1]] = t[i]-t[i-1]
N_CORTES = len(corte); T_SIN = sum(corte.values())
print(f"Cortes de señal GPS: {N_CORTES} | tiempo sin señal {T_SIN/60:.1f} min ({T_SIN:.0f} s)")
cd = [0.0]
for i in range(1, n): cd.append(cd[-1] + (hv(lat[i-1], lon[i-1], lat[i], lon[i]) if seg[i] == seg[i-1] else 0.0))
T0 = t[0]
tt = sum((t[i]-t[i-1]) for i in range(1, n) if seg[i] == seg[i-1])
plan = sum((t[i]-t[i-1]) for i in range(1, n) if seg[i] == seg[i-1] and (v[i]+v[i-1])/2 > 7)
navv = sum((t[i]-t[i-1])*(v[i]+v[i-1])/2 for i in range(1, n) if seg[i] == seg[i-1] and (v[i]+v[i-1])/2 > 7) / plan if plan else 0
nav4 = sum((t[i]-t[i-1]) for i in range(1, n) if seg[i] == seg[i-1] and (v[i]+v[i-1])/2 > 4)
navv4 = sum((t[i]-t[i-1])*(v[i]+v[i-1])/2 for i in range(1, n) if seg[i] == seg[i-1] and (v[i]+v[i-1])/2 > 4) / nav4 if nav4 else 0
print(f"Navegando (>4 kn) {nav4/60:.1f} min | vel. media navegando {navv4:.2f} kn")
print(f"Tiempo {tt/60:.1f} min | Dist {cd[-1]/1000:.2f} km | Planeo {plan/60:.1f} min ({plan/tt*100:.1f}%) | Vel media en planeo (>7 kn) {navv:.2f} kn | puntos {n} | segmentos {seg[-1]+1}")
# VELOCIDAD MÁXIMA EN 20 m: media de la velocidad GPS de los puntos de cada tramo de 20 m (mismo segmento); se toma el máximo
ps = [0.0]
for x in v: ps.append(ps[-1] + x)
vmax20 = (0.0, 0, 0); k2 = 0
for i0_ in range(n):
    k2 = max(k2, i0_)
    if k2 > i0_ and seg[k2] != seg[i0_]: k2 = i0_
    while k2+1 < n and seg[k2+1] == seg[i0_] and cd[k2]-cd[i0_] < 20: k2 += 1
    if cd[k2]-cd[i0_] >= 20:
        m_ = (ps[k2+1]-ps[i0_])/(k2-i0_+1)
        if m_ > vmax20[0]: vmax20 = (m_, i0_, k2)
VM20, VM20a, VM20b = vmax20
print(f"Velocidad máxima en 20 m: {VM20:.2f} kn")
track = [{'t': t[i], 'lat': lat[i], 'lon': lon[i], 'speed_kn': v[i], 'cumdist': cd[i], 'seg': seg[i]} for i in range(n)]

# 3) RUMBO (COG) por posición, ventana de 15 m
cog = [None]*n; j = 0
for i in range(n):
    if seg[j] != seg[i]: j = i
    while j < i and cd[i]-cd[j] > 15: j += 1
    if cd[i]-cd[j] < 4.5: continue
    cog[i] = brg(lat[j], lon[j], lat[i], lon[i])
iv = [i for i in range(n) if cog[i] is not None]; tv = [t[i] for i in iv]
def avgh(a, b, sg):
    pts = [i for i in iv[bisect.bisect_left(tv, a):bisect.bisect_right(tv, b)] if seg[i] == sg]
    if not pts: return None
    sx = sum(math.sin(math.radians(cog[i])) for i in pts); sy = sum(math.cos(math.radians(cog[i])) for i in pts)
    return (math.degrees(math.atan2(sx, sy)) + 360) % 360

# 4) CANDIDATOS: cambio de rumbo >= 55° (promedio 10-3 s antes vs 3-10 s después); runs < 8 s = 1 evento
flag = []
for i in iv:
    hb = avgh(t[i]-10, t[i]-3, seg[i]); ha = avgh(t[i]+3, t[i]+10, seg[i])
    if hb is None or ha is None: continue
    d = ((ha-hb)+180) % 360 - 180
    if abs(d) >= 55: flag.append((i, abs(d)))
events = []; k = 0
while k < len(flag):
    s = k
    while k+1 < len(flag) and t[flag[k+1][0]] - t[flag[k][0]] < 8: k += 1
    events.append(max(flag[s:k+1], key=lambda x: x[1])[0]); k += 1

# 5) CLASIFICACIÓN con el camino REAL del rumbo (unwrap continuo, ±18 s). NUNCA "camino más corto".
def classify(tc, sg, hw=18):
    pts = [i for i in iv[bisect.bisect_left(tv, tc-hw):bisect.bisect_right(tv, tc+hw)] if seg[i] == sg]
    if len(pts) < 4: return None
    uw = {pts[0]: cog[pts[0]]}
    for a, b in zip(pts, pts[1:]): uw[b] = uw[a] + ((cog[b]-cog[a]) + 180) % 360 - 180
    bc = [i for i in pts if t[i] <= tc-2]; ac = [i for i in pts if t[i] >= tc+2]
    if not bc or not ac: return None
    ub, ua = uw[bc[0]], uw[ac[-1]]
    if abs(ua-ub) < 50: return 'pequeno'
    ct = math.floor((ub-WIND_FROM)/360) != math.floor((ua-WIND_FROM)/360)   # cruza proa-al-viento
    cg = math.floor((ub-DOWNWIND)/360) != math.floor((ua-DOWNWIND)/360)     # cruza popa-al-viento
    if ct and not cg: return 'Virada'
    if cg and not ct: return 'Trasluchada'
    return 'complejo'          # no cruza limpiamente ningún eje -> se EXCLUYE del informe
cand = []
for i in events:
    ty = classify(t[i], seg[i])
    if ty in (None, 'pequeno', 'complejo'): continue
    cand.append({'tipo': ty, 't': t[i], 'lat': lat[i], 'lon': lon[i]})

# 6) EVENTOS CON PARADA (v < 2.5 kn >= 4 s): tipo por rumbo 30 m antes/después (camino angular más corto, solo aquí)
def contains(hb, diff, tg):
    rel = (tg-hb) % 360
    return rel <= diff + 1e-6 if diff >= 0 else rel >= 360 + diff - 1e-6
def bb(i, dm=30):
    j = i
    while j > 0 and seg[j-1] == seg[i] and cd[j] > cd[i]-dm: j -= 1
    return None if j == i else brg(lat[j], lon[j], lat[i], lon[i])
def ba(i, dm=30):
    k = i
    while k < n-1 and seg[k+1] == seg[i] and cd[k] < cd[i]+dm: k += 1
    return None if k == i else brg(lat[i], lon[i], lat[k], lon[k])
i = 0; caidas = []
while i < n:
    if v[i] < 2.5:
        j = i
        while j < n and v[j] < 2.5 and seg[j] == seg[i]: j += 1
        if t[j-1]-t[i] >= 4:
            hb = bb(i); ha = ba(j-1)
            if hb is not None and ha is not None:
                d = ((ha-hb)+180) % 360 - 180
                if abs(d) >= 50:
                    a = contains(hb, d, WIND_FROM); b = contains(hb, d, DOWNWIND)
                    if a and not b: caidas.append({'tipo': 'Virada', 't': t[i], 'lat': lat[i], 'lon': lon[i]})
                    elif b and not a: caidas.append({'tipo': 'Trasluchada', 't': t[i], 'lat': lat[i], 'lon': lon[i]})
        i = j
    else: i += 1

# 7) UNIÓN, deduplicado (<15 s), velocidades, COMPLETA/FALLIDA, filtro de entrada (wingfoil >= 6 kn, windsurf >= 4 kn)
allm = [m for m in caidas if m['t']-T0 > 90] + cand
allm.sort(key=lambda m: m['t'])
dd = []
for m in allm:
    if dd and abs(m['t']-dd[-1]['t']) < 15: continue
    dd.append(m)
SG = 0
def avg(a, b):
    vals = [v[i] for i in range(n) if a <= cd[i] <= b and seg[i] == SG]
    return sum(vals)/len(vals) if vals else None
def blanco(a, b):                      # caída SOSTENIDA: >= 2 muestras seguidas < 4 kn
    r = 0
    for i in range(n):
        if a <= cd[i] <= b and seg[i] == SG:
            if v[i] < 4:
                r += 1
                if r >= 2: return True
            else: r = 0
    return False
def twa(h):                            # ángulo al viento: 0° = proa al viento, 90° = través, 180° = popa
    return abs(((h - WIND_FROM) + 180) % 360 - 180)
def ang_t(i, antes):                   # rumbo promedio 10-3 s antes (o 3-10 s después) del giro, mismo segmento
    tc = t[i]
    h = avgh(tc-10, tc-3, seg[i]) if antes else avgh(tc+3, tc+10, seg[i])
    return None if h is None else round(twa(h))      # grados enteros: la variación cuadra con lo que se ve
def _uw(tc, sg, hw=18):                 # rumbo "desenrollado" (continuo) alrededor del giro: [(índice, grados)]
    pts = [i for i in iv[bisect.bisect_left(tv, tc-hw):bisect.bisect_right(tv, tc+hw)] if seg[i] == sg]
    if len(pts) < 4: return []
    out = [(pts[0], cog[pts[0]])]
    for a, b in zip(pts, pts[1:]): out.append((b, out[-1][1] + ((cog[b]-cog[a]) + 180) % 360 - 180))
    return out
UPX, UPY = math.sin(math.radians(WIND_FROM)), math.cos(math.radians(WIND_FROM))   # vector hacia DONDE VIENE el viento
KX = math.cos(math.radians(lat[0])) * 111320.0; KY = 110574.0
def geom(i, vi):
    """Cómo fue el giro: inicio y fin (rumbo a menos de 15° del de entrada / salida), duración, radio,
    velocidad mínima, metros ganados (+) o cedidos (−) contra el viento y tiempo hasta recuperar el 80% de la velocidad."""
    tc, sg = t[i], seg[i]
    U = _uw(tc, sg)
    r = {'dur': None, 'radio': None, 'vmin': None, 'barlo': None, 't_rec': None, 'ti': None, 'tf': None}
    if not U: return r
    hb = [u for q, u in U if tc-10 <= t[q] <= tc-3]; ha = [u for q, u in U if tc+3 <= t[q] <= tc+10]
    if not hb or not ha: return r
    hb = sum(hb)/len(hb); ha = sum(ha)/len(ha)
    ini = [q for q, u in U if t[q] <= tc and abs(u-hb) <= 15]
    fn_ = [q for q, u in U if t[q] >= tc and abs(u-ha) <= 15]
    qi = ini[-1] if ini else U[0][0]; qf = fn_[0] if fn_ else U[-1][0]
    if t[qf] <= t[qi]: return r
    r['ti'], r['tf'] = t[qi], t[qf]
    r['dur'] = t[qf] - t[qi]
    giro = abs(dict(U)[qf] - dict(U)[qi])
    if giro >= 30: r['radio'] = (cd[qf]-cd[qi]) / math.radians(giro)
    r['vmin'] = min(v[q] for q in range(qi, qf+1) if seg[q] == sg)
    dx = (lon[qf]-lon[qi])*KX; dy = (lat[qf]-lat[qi])*KY
    r['barlo'] = dx*UPX + dy*UPY
    q = i                                    # recuperación: media de 3 puntos >= 80% de la velocidad de entrada (hasta 60 s)
    while q+2 < n and seg[q+2] == sg and t[q] <= tc + 60:
        if t[q] >= t[qf] - 1 and (v[q]+v[q+1]+v[q+2])/3 >= 0.8*vi: r['t_rec'] = t[q] - tc; break
        q += 1
    return r
def parada(ta, tb, vlim, dmin, sg):         # ¿hay una racha con velocidad < vlim de dmin s o más entre ta y tb?
    q = bisect.bisect_left(t, ta)
    while q < n and t[q] <= tb:
        if seg[q] == sg and v[q] < vlim:
            k = q
            while k+1 < n and seg[k+1] == sg and v[k+1] < vlim: k += 1
            if t[k] - t[q] >= dmin: return True
            q = k + 1
        else: q += 1
    return False
fin = []
for m in dd:
    i = min(range(n), key=lambda q: abs(t[q]-m['t'])); c0 = cd[i]; SG = seg[i]
    vi = avg(c0-40, c0); vo = avg(c0, c0+40)
    if vi is None or vi < V_ENT_MIN: continue      # no venía navegando (wingfoil: no estaba foileando)
    fin_seg = max(cd[q] for q in range(i, n) if seg[q] == SG)
    cayo_agua = SG in corte and fin_seg < c0 + 40          # la señal se corta (teléfono bajo el agua) antes de 40 m
    ai_, ao_ = ang_t(i, True), ang_t(i, False)
    if m['tipo'] == 'Trasluchada':       # trasluchada: grados respecto a la popa redonda (180° al viento)
        ai_, ao_ = (None if ai_ is None else 180 - ai_), (None if ao_ is None else 180 - ao_)
    m.update({'ang_in': ai_, 'ang_out': ao_})   # virada: grados respecto al enfachado (proa al viento)
    h_in = avgh(t[i]-10, t[i]-3, seg[i])         # de qué lado venía el viento antes del giro (amura de entrada)
    if h_in is None: h_in = avgh(t[i]-18, t[i]-3, seg[i])
    m['amura'] = None if h_in is None else ('estribor' if 0 < (WIND_FROM - h_in) % 360 < 180 else 'babor')
    g_ = geom(i, vi); m.update(g_)
    if WS:
        # windsurf: en la virada es normal quedar casi parado; se considera caída quedarse < 1,5 kn 12 s o más
        # (levantar la vela / waterstart) o no volver a 4 kn en 60 s. En la trasluchada: < 2 kn 6 s o más.
        if m['tipo'] == 'Virada':
            caida_ = parada(t[i]-5, t[i]+60, 1.5, 12, SG) or not any(v[q] >= 4 for q in range(i, n) if seg[q] == SG and t[q] <= t[i]+60)
        else:
            caida_ = parada(t[i]-5, t[i]+40, 2.0, 6, SG)
    else:
        caida_ = blanco(c0, c0+40)
    m.update({'resultado': 'Fallida' if (caida_ or cayo_agua) else 'Completa', 'v_in': vi, 'v_out': vo,
              'nota': 'corte de señal tras el giro' if cayo_agua else ''})
    m['planeo'] = (None if WS or m['vmin'] is None else m['vmin'] >= 7)      # wingfoil: no bajó de 7 kn en todo el giro
    fin.append(m)
c = {}
for m in fin:
    key = m['tipo']; c[key] = c.get(key, 0) + 1          # numeración consecutiva por tipo (completas y fallidas juntas)
    m['numero_grupo'] = c[key]; m['nombre'] = f"{m['tipo']} #{c[key]} ({m['resultado']})"
print(Counter((m['tipo'], m['resultado']) for m in fin))
for ty_ in ('Trasluchada', 'Virada'):
    L_ = [m for m in fin if m['tipo'] == ty_ and m['resultado'] == 'Completa']      # velocidades: solo completas
    if not L_: print(f"{ty_}s: sin maniobras completas"); continue
    vi_ = [m['v_in'] for m in L_]; vo_ = [m['v_out'] for m in L_ if m['v_out'] is not None]
    va_ = [(m['v_out']-m['v_in'])/m['v_in'] for m in L_ if m['v_out'] is not None and m['v_in']]
    print(f"{ty_}s completas ({len(L_)}): entrada media {sum(vi_)/len(vi_):.2f} kn | salida media {sum(vo_)/len(vo_):.2f} kn | variación media {sum(va_)/len(va_)*100:+.1f}%")
M = fin

# 7b) NAVEGACIÓN ENTRE MANIOBRAS: rumbos respecto al viento, ángulo de ceñida y de largo por amura, VMG.
#     Se usan los puntos con rumbo y velocidad >= V_NAV (wingfoil 7 kn = en planeo; windsurf 4 kn = navegando),
#     fuera de los 12 s alrededor de cada maniobra y de cada parada.
_lejos = sorted([m['t'] for m in M] + [x['t'] for x in caidas])
def _cerca(tq):
    k = bisect.bisect_left(_lejos, tq - 12)
    return k < len(_lejos) and _lejos[k] <= tq + 12
RUMBOS = [('Ceñida', 0, 70), ('Través', 70, 110), ('Largo', 110, 150), ('Popa', 150, 181)]
NAVP = []          # (t, dt, v, twa, lado)
for k in range(1, n):
    i = k
    if cog[i] is None or seg[i] != seg[i-1] or v[i] < V_NAV or _cerca(t[i]): continue
    dt_ = min(t[i]-t[i-1], 2.0)
    NAVP.append((t[i], dt_, v[i], twa(cog[i]), 'estribor' if 0 < (WIND_FROM - cog[i]) % 360 < 180 else 'babor', seg[i]))
def _medp(xs):                                  # mediana ponderada por tiempo: [(valor, peso)]
    xs = sorted(xs); tot = sum(w for _, w in xs)
    if not tot: return None
    acc = 0
    for x, w in xs:
        acc += w
        if acc >= tot/2: return x
TNAV = sum(p_[1] for p_ in NAVP)
rumbos = []
for nm_, a_, b_ in RUMBOS:
    P_ = [p_ for p_ in NAVP if a_ <= p_[3] < b_]
    tt_ = sum(p_[1] for p_ in P_)
    lados = {}
    for ld in ('babor', 'estribor'):
        Q_ = [p_ for p_ in P_ if p_[4] == ld]; tq_ = sum(p_[1] for p_ in Q_)
        lados[ld] = (sum(p_[1]*p_[2] for p_ in Q_)/tq_) if tq_ else None
    rumbos.append({'rumbo': nm_, 'desde': a_, 'hasta': min(b_, 180), 'min': tt_/60, 'pct': (tt_/TNAV) if TNAV else None,
                   'v_media': (sum(p_[1]*p_[2] for p_ in P_)/tt_) if tt_ else None, 'v_max': max((p_[2] for p_ in P_), default=None),
                   'v_babor': lados['babor'], 'v_estribor': lados['estribor']})
angulos = {}
for ld in ('babor', 'estribor'):
    up_ = [(p_[3], p_[1]) for p_ in NAVP if p_[4] == ld and p_[3] < 90]
    dn_ = [(p_[3], p_[1]) for p_ in NAVP if p_[4] == ld and p_[3] > 90]
    vu_ = [(p_[2]*math.cos(math.radians(p_[3])), p_[1]) for p_ in NAVP if p_[4] == ld and p_[3] < 90]
    vd_ = [(-p_[2]*math.cos(math.radians(p_[3])), p_[1]) for p_ in NAVP if p_[4] == ld and p_[3] > 90]
    angulos[ld] = {'cenida': _medp(up_), 'largo': _medp(dn_),
                   'vmg_up': (sum(x*w for x, w in vu_)/sum(w for _, w in vu_)) if vu_ else None,
                   'vmg_dn': (sum(x*w for x, w in vd_)/sum(w for _, w in vd_)) if vd_ else None,
                   'min_up': sum(w for _, w in up_)/60, 'min_dn': sum(w for _, w in dn_)/60}
def _mejor_vmg(signo):                          # mejor VMG sostenido 10 s (puntos consecutivos del mismo segmento)
    best = (None, None); j0 = 0; acc = 0.0; accw = 0.0
    for j in range(len(NAVP)):
        if j > 0 and (NAVP[j][5] != NAVP[j-1][5] or NAVP[j][0] - NAVP[j-1][0] > 3): j0 = j; acc = accw = 0.0
        x = signo * NAVP[j][2] * math.cos(math.radians(NAVP[j][3])); acc += x*NAVP[j][1]; accw += NAVP[j][1]
        while NAVP[j][0] - NAVP[j0][0] > 10:
            acc -= signo * NAVP[j0][2] * math.cos(math.radians(NAVP[j0][3])) * NAVP[j0][1]; accw -= NAVP[j0][1]; j0 += 1
        if NAVP[j][0] - NAVP[j0][0] >= 8 and accw > 0 and (best[0] is None or acc/accw > best[0]): best = (acc/accw, NAVP[j][0])
    return best
VMGU, VMGU_T = _mejor_vmg(1); VMGD, VMGD_T = _mejor_vmg(-1)
print(f"Navegación medida ({'>= %g kn' % V_NAV}): {TNAV/60:.1f} min | ceñida babor {angulos['babor']['cenida']} / estribor {angulos['estribor']['cenida']} | "
      f"mejor VMG 10 s contra el viento {VMGU} / a favor {VMGD}")

# 8) SALTOS con el acelerómetro (TotalAcceleration.csv, opcional: Sensor Logger o Wingfoil Tracker >= 1.5)
#    En el aire el teléfono (en el pecho) marca mucho menos de 1 g: queda solo el tirón del ala.
#    SALTO = |a| (media móvil de 0.1 s) bajo 7 m/s² (0.7 g) durante --salto-min s o más (1.0 s) Y altura estimada
#    >= --salto-h-min (0.5 m). Con oleaje (01-11-2026) el cuerpo se descarga al pasar una ola hasta 0.8 s y
#    ~0.5 g, con altura estimada <= 0.46 m: no cuenta. Altura máx. h = (g - a_media) * t² / 8;
#    distancia en vuelo = velocidad GPS al despegar * t.
#    Salto FALLIDO = en los 10 s posteriores al aterrizaje la velocidad cae bajo 4 kn por más de 5 s,
#    o la señal GPS se corta más de 5 s (teléfono bajo el agua). Si no, salto COMPLETO.
G = 9.81; A_LOW = 7.0; SALTO_MIN = A.salto_min
SALTOS = []; ACC_OK = False
acc_f = None
if A.location.lower().endswith('.zip'): acc_f = _abrir(A.location, 'TotalAcceleration.csv')
else:
    _pth = os.path.join(os.path.dirname(os.path.abspath(A.location)), 'TotalAcceleration.csv')
    if os.path.exists(_pth): acc_f = open(_pth, encoding='utf-8-sig')
if acc_f:
    hdr = [h_.strip() for h_ in acc_f.readline().split(',')]
    try: it_, ix_, iy_, iz_ = hdr.index('time'), hdr.index('x'), hdr.index('y'), hdr.index('z')
    except ValueError: it_ = None
    ta = array.array('d'); am = array.array('d')
    if it_ is not None:
        for line in acc_f:
            q = line.split(',')
            try:
                tt_ = int(q[it_]) / 1e9 - EP; x_ = float(q[ix_]); y_ = float(q[iy_]); z_ = float(q[iz_])
            except (ValueError, IndexError): continue
            ta.append(tt_); am.append(math.sqrt(x_*x_ + y_*y_ + z_*z_))
    if len(ta) > 1000:
        ACC_OK = True
        fs = (len(ta) - 1) / max(ta[-1] - ta[0], 1e-9)
        kw = max(1, int(round(0.1 * fs)))                    # media móvil de 0.1 s
        cs_ = [0.0]
        for x_ in am: cs_.append(cs_[-1] + x_)
        NA = len(am); h2 = kw // 2
        def sm(i): a_ = max(0, i - h2); b_ = min(NA, i + kw - h2); return (cs_[b_] - cs_[a_]) / (b_ - a_)
        runs = []; i = 0
        while i < NA:
            if sm(i) < A_LOW:
                j = i
                while j < NA and sm(j) < A_LOW: j += 1
                if runs and ta[i] - ta[runs[-1][1] - 1] < 0.12: runs[-1] = (runs[-1][0], j)   # une cortes breves
                else: runs.append((i, j))
                i = j
            else: i += 1
        for i0_, j0_ in runs:
            dur = ta[j0_ - 1] - ta[i0_]
            if dur < SALTO_MIN: continue
            a_med = sum(am[i0_:j0_]) / (j0_ - i0_)
            h_ = max(0.0, G - a_med) * dur * dur / 8
            if h_ < A.salto_h_min: continue
            ts_ = ta[i0_]; te_ = ta[j0_ - 1]
            if ts_ < t[0] or ts_ > t[-1] or any(a_ <= ts_ <= b_ for a_, b_ in EXC): continue
            k_ = bisect.bisect_left(t, ts_); k_ = min(max(k_, 0), n - 1)
            if k_ > 0 and abs(t[k_-1] - ts_) < abs(t[k_] - ts_): k_ -= 1
            if abs(t[k_] - ts_) > 3: continue                         # sin GPS cerca
            v_in = v[k_]
            if v_in < 7: continue                                     # solo navegando en planeo
            imp = max(am[j0_:min(NA, j0_ + int(0.6 * fs) + 1)] or [0])
            desp = [i for i in range(k_, n) if te_ + 1 <= t[i] <= te_ + 5 and seg[i] == seg[k_]]
            v_out = sum(v[i] for i in desp) / len(desp) if desp else None
            # ¿fallido? se mira desde el aterrizaje hasta 10 s después (una racha lenta puede seguir más allá)
            fallido = False; nota_ = ''
            prev_ = max(k_, bisect.bisect_right(t, te_) - 1)
            i = prev_ + 1
            if i >= n or seg[i] != seg[prev_] or t[i] - max(te_, t[prev_]) > 5:
                fallido = True; nota_ = 'corte de señal tras el aterrizaje'
            else:
                q_ = prev_ + 1                                         # corte de señal > 5 s dentro de los 10 s
                while q_ < n and t[q_ - 1] <= te_ + 10:
                    if seg[q_] != seg[q_ - 1] or t[q_] - t[q_ - 1] > 5:
                        fallido = True; nota_ = 'corte de señal tras el aterrizaje'; break
                    q_ += 1
                if q_ >= n and t[n - 1] < te_ + 10: fallido = True; nota_ = 'corte de señal tras el aterrizaje'
                while i < n and seg[i] == seg[prev_] and t[i] <= te_ + 10 and not fallido:
                    if v[i] < 4:
                        j = i
                        while j + 1 < n and seg[j+1] == seg[i] and v[j+1] < 4 and t[j+1] - t[j] <= 5: j += 1
                        fin_ = (j + 1 >= n or seg[j+1] != seg[i] or t[j+1] - t[j] > 5)    # la racha termina en un corte
                        if t[j] - t[i] > 5 or fin_:
                            fallido = True; nota_ = 'velocidad < 4 kn más de 5 s' if not fin_ else 'velocidad < 4 kn y corte de señal'
                        i = j + 1
                    else: i += 1
            SALTOS.append({'t': ts_, 'aire': dur, 'altura': h_, 'dist': v_in / K * dur, 'v_in': v_in, 'v_out': v_out, 'impacto_g': imp / G,
                           'lat': lat[k_], 'lon': lon[k_], 'cd': cd[k_], 'resultado': 'Fallido' if fallido else 'Completo', 'nota': nota_})
        for i_, e_ in enumerate(SALTOS, 1): e_['nombre'] = f"Salto #{i_} ({e_['resultado']})"
    print(f"Saltos (vuelo >= {SALTO_MIN:g} s y >= {A.salto_h_min:g} m): {len(SALTOS)} | completos {sum(e_['resultado'] == 'Completo' for e_ in SALTOS)} | fallidos {sum(e_['resultado'] == 'Fallido' for e_ in SALTOS)}" +
          (f" | más alto {max(e_['altura'] for e_ in SALTOS):.2f} m" if SALTOS else ''))
else:
    print("Saltos: sin datos de acelerómetro (TotalAcceleration.csv)")

# 8) SALIDAS: KML + Excel
FECHA = A.fecha; VIENTO = f"{WIND_FROM:.0f}°"
os.makedirs(A.outdir, exist_ok=True)
def hora(tt_): return (datetime.datetime.fromtimestamp(EP+tt_, datetime.timezone.utc) + datetime.timedelta(hours=UTC)).strftime('%H:%M:%S')
def esc(s): return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
NS = A.sections; sl = track[-1]['cumdist']/NS
def bk(x): return 0 if x < 4 else 1 if x < 7 else 2 if x < 12 else 3
def sec(d): return min(int(d//sl), NS-1)
binfo = {0: ("ffffffff", "Blanco (menos de 4 nudos)"), 1: ("ff00ff00", "Verde (4 a 7 nudos)"), 2: ("ff00ffff", "Amarillo (7 a 12 nudos)"), 3: ("ff0000ff", "Rojo (mas de 12 nudos)")}
segs = []; cs = sec(track[0]['cumdist']); cb = None; cc = []
for a, b in zip(track, track[1:]):
    bu = bk((a['speed_kn']+b['speed_kn'])/2); s = sec((a['cumdist']+b['cumdist'])/2)
    if a['seg'] != b['seg']:
        if len(cc) > 1: segs.append((cs, cb, cc))
        cc = []; cb = None; continue
    if (s, bu) != (cs, cb) or not cc:
        if len(cc) > 1: segs.append((cs, cb, cc))
        cc = [(a['lon'], a['lat'])]; cs, cb = s, bu
    cc.append((b['lon'], b['lat']))
if len(cc) > 1: segs.append((cs, cb, cc))
icons = {('Virada', 'Completa'): ('grn-stars', 'Virada COMPLETA (sin caída)'), ('Virada', 'Fallida'): ('red-stars', 'Virada FALLIDA (con caída)'),
         ('Trasluchada', 'Completa'): ('grn-circle', 'Trasluchada COMPLETA (sin caída)'), ('Trasluchada', 'Fallida'): ('orange-circle', 'Trasluchada FALLIDA (con caída)')}
_vkn = f" · {A.viento_kn:g} kn" if A.viento_kn is not None else ''
_desc = " · ".join(x for x in (FECHA, A.lugar, f"Viento desde {VIENTO}{_vkn}") if x) + (f"<br/>{esc(A.comentario)}" if A.comentario else '')
k_ = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2">', '<Document>',
      f'<name>{esc(A.nombre) if A.nombre else "Track " + DISC + " " + FECHA}</name>', f'<description><![CDATA[{_desc}]]></description>']
for b, (col, l) in binfo.items(): k_.append(f'<Style id="line{b}"><LineStyle><color>{col}</color><width>4</width></LineStyle></Style>')
for key, (ic, _) in icons.items(): k_.append(f'<Style id="{ic}"><IconStyle><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/{ic}.png</href></Icon></IconStyle></Style>')
for s in range(NS):
    k_.append(f'<Folder><name>Seccion {s+1} de {NS} ({s*sl/1000:.1f}-{(s+1)*sl/1000:.1f} km)</name>')
    for b, (col, l) in binfo.items():
        k_.append(f'<Folder><name>{esc(l)}</name>')
        for ss, sb, co in segs:
            if ss == s and sb == b:
                k_.append(f'<Placemark><styleUrl>#line{b}</styleUrl><LineString><tessellate>1</tessellate><coordinates>' + " ".join(f"{x:.7f},{y:.7f},0" for x, y in co) + '</coordinates></LineString></Placemark>')
        k_.append('</Folder>')
    k_.append('</Folder>')
k_.append('<Folder><name>Maniobras</name>')
for key, (ic, nm) in icons.items():
    L = [m for m in M if (m['tipo'], m['resultado']) == key]
    if not L: continue
    k_.append(f'<Folder><name>{esc(nm)} ({len(L)})</name>')
    for m in L:
        h = hora(m['t']); d = f"Hora: {h}<br/>Vel. entrada (40m): {m['v_in']:.1f} kn | Vel. salida (40m): {('%.1f' % m['v_out']) if m['v_out'] is not None else 's/d'} kn" + (f"<br/>Ángulo respecto {'a la popa redonda' if m['tipo'] == 'Trasluchada' else 'al enfachado'}: entrada (10-3 s antes) {('%.0f°' % m['ang_in']) if m['ang_in'] is not None else 's/d'} | salida (3-10 s después) {('%.0f°' % m['ang_out']) if m['ang_out'] is not None else 's/d'}") + (f"<br/>Viento por {m['amura']} antes del giro" if m.get('amura') else '') + (f"<br/>Vel. mínima en el giro: {m['vmin']:.1f} kn" if m.get('vmin') is not None else '') + (f" | duración {m['dur']:.0f} s" if m.get('dur') is not None else '') + (f" | radio {m['radio']:.0f} m" if m.get('radio') is not None else '') + (f"<br/>Contra el viento: {m['barlo']:+.0f} m" if m.get('barlo') is not None else '') + (f" | recupera el 80% de la velocidad en {m['t_rec']:.0f} s" if m.get('t_rec') is not None else '') + ("<br/>En planeo: no bajó de 7 kn" if m.get('planeo') else '') + (f"<br/>Nota: {m['nota']}" if m['nota'] else '')
        k_.append(f'<Placemark><name>{esc(m["tipo"])} #{m["numero_grupo"]} — {h} ({m["resultado"]})</name><description><![CDATA[{d}]]></description><styleUrl>#{ic}</styleUrl><Point><coordinates>{m["lon"]:.7f},{m["lat"]:.7f},0</coordinates></Point></Placemark>')
    k_.append('</Folder>')
k_.append('</Folder>')
if SALTOS:
    k_.append('<Style id="saltoC"><IconStyle><scale>1.2</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-blank.png</href></Icon></IconStyle></Style>')
    k_.append('<Style id="saltoF"><IconStyle><scale>1.2</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/pink-blank.png</href></Icon></IconStyle></Style>')
    k_.append(f'<Folder><name>Saltos ({len(SALTOS)})</name>')
    for res_, sty_, tit_ in (('Completo', 'saltoC', 'Salto COMPLETO (sigue navegando)'), ('Fallido', 'saltoF', 'Salto FALLIDO (con caída)')):
        L_ = [e_ for e_ in SALTOS if e_['resultado'] == res_]
        if not L_: continue
        k_.append(f'<Folder><name>{tit_} ({len(L_)})</name>')
        for e_ in L_:
            d_ = (f"Hora: {hora(e_['t'])}<br/>Tiempo en vuelo: {e_['aire']:.2f} s<br/>Altura máxima estimada: {e_['altura']:.2f} m<br/>Distancia en vuelo: {e_['dist']:.1f} m<br/>Velocidad: {e_['v_in']:.1f} kn"
                  + (f"<br/>Nota: {e_['nota']}" if e_['nota'] else ''))
            nm_ = e_['nombre'].split(' (')[0]
            k_.append(f'<Placemark><name>{nm_} — {e_["altura"]:.1f} m — {hora(e_["t"])} ({res_})</name><description><![CDATA[{d_}]]></description><styleUrl>#{sty_}</styleUrl><Point><coordinates>{e_["lon"]:.7f},{e_["lat"]:.7f},0</coordinates></Point></Placemark>')
        k_.append('</Folder>')
    k_.append('</Folder>')
k_.append('<Style id="vmax"><IconStyle><scale>1.3</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/purple-stars.png</href></Icon></IconStyle></Style>')
k_.append(f'<Placemark><name>Velocidad máxima 20 m: {VM20:.1f} kn — {hora(t[VM20a])}</name><description><![CDATA[Media de la velocidad GPS en el tramo de 20 m de mayor velocidad ({hora(t[VM20a])} a {hora(t[VM20b])}).]]></description><styleUrl>#vmax</styleUrl><Point><coordinates>{lon[VM20a]:.7f},{lat[VM20a]:.7f},0</coordinates></Point></Placemark>')
k_ += ['</Document>', '</kml>']
kml_path = os.path.join(A.outdir, f'track_{A.disciplina}_{FECHA}_maniobras.kml'); open(kml_path, 'w', encoding='utf-8').write("\n".join(k_))

F = 'Arial'; HF = PatternFill('solid', fgColor='1F4E78'); HFo = Font(name=F, bold=True, color='FFFFFF', size=10); N = Font(name=F, size=10); B = Font(name=F, bold=True, size=10)
bd = Border(*(Side(style='thin', color='CCCCCC'),)*4)
fills = {('Virada', 'Completa'): 'C6EFCE', ('Virada', 'Fallida'): 'FFC7CE', ('Trasluchada', 'Completa'): 'DDEBF7', ('Trasluchada', 'Fallida'): 'FCE4D6'}
wb = Workbook(); wt = wb.active; wt.title = 'Track'
for ci, h in enumerate(['t_seg', 'lat', 'lon', 'velocidad_kn', 'dist_acum_m', 'dt_seg', 'vel_media_seg_kn', 'dt_navegando_seg' if WS else 'dt_planeo_seg', 'segmento', 'dt_x_vel_navegando' if WS else 'dt_x_vel_planeo'], 1):
    x = wt.cell(1, ci, h); x.font = HFo; x.fill = HF
for r, p in enumerate(track, 2):
    for ci, val in enumerate([round(p['t'], 3), round(p['lat'], 7), round(p['lon'], 7), round(p['speed_kn'], 3), round(p['cumdist'], 2)], 1): wt.cell(r, ci, val).font = N
    wt.cell(r, 9, p['seg'] + 1).font = N
    if r > 2:
        wt.cell(r, 6, f"=IF(I{r}=I{r-1},A{r}-A{r-1},0)"); wt.cell(r, 7, f"=AVERAGE(D{r-1}:D{r})"); wt.cell(r, 8, f"=IF(G{r}>{4 if WS else 7},F{r},0)")
        wt.cell(r, 10, f"=H{r}*G{r}")
LR = len(track)+1; wt.freeze_panes = 'A2'
wm = wb.create_sheet('Maniobras', 0); wm.sheet_view.showGridLines = False
wm['A1'] = f'Track {DISC} {FECHA} — Viradas y Trasluchadas (Completa vs Fallida)'; wm['A1'].font = Font(name=F, bold=True, size=14)
wm['A2'] = (f'{DISC} · viento desde {VIENTO}. ' + wf_textos.buscar(wf_textos.maniobras(WS), 'Resultado') +
            f' Se excluyen las maniobras con velocidad de entrada (40 m previos) menor a {V_ENT_MIN:g} kn y los giros que no cruzan limpiamente ningún eje. Qué es y para qué sirve cada columna: hoja Glosario.')
wm.merge_cells('A2:T2'); wm.row_dimensions[2].height = 52; wm['A2'].font = Font(name=F, italic=True, size=9, color='555555'); wm['A2'].alignment = Alignment(wrap_text=True, vertical='top')
for ci, h in enumerate(['Nombre (igual que en el KML)', 'Tipo', 'Resultado', 'Tiempo transcurrido', 'Hora local', 'Latitud', 'Longitud', 'Vel. entrada 40m (kn)', 'Vel. salida 40m (kn)', 'Variación salida vs entrada (%)', 'Ángulo de entrada al eje, 10-3 s antes (°)', 'Ángulo de salida del eje, 3-10 s después (°)', 'Viento por (antes del giro)', 'Observación', 'Vel. mínima en el giro (kn)', 'Duración del giro (s)', 'Radio del giro (m)', 'Metros contra el viento (+ ganados / − cedidos)', 'Recuperación al 80% de la vel. de entrada (s)', *([] if WS else ['En planeo (no bajó de 7 kn)'])], 1):
    x = wm.cell(4, ci, h); x.font = HFo; x.fill = HF; x.border = bd; x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
wm.row_dimensions[4].height = 44
for r, m in enumerate(M, 5):
    tr = m['t']-T0; fl = PatternFill('solid', fgColor=fills[(m['tipo'], m['resultado'])])
    vals = [m['nombre'], m['tipo'], m['resultado'], f"{int(tr//60):02d}:{int(tr%60):02d}", hora(m['t']), round(m['lat'], 6), round(m['lon'], 6), round(m['v_in'], 2), round(m['v_out'], 2) if m['v_out'] is not None else None]
    for ci, val in enumerate(vals, 1):
        x = wm.cell(r, ci, val); x.font = N; x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='left' if ci == 1 else 'center')
    for ci, val in ((11, m['ang_in']), (12, m['ang_out'])):
        x = wm.cell(r, ci, round(val, 0) if val is not None else None); x.font = N; x.fill = fl; x.border = bd
        x.alignment = Alignment(horizontal='center'); x.number_format = '0"°"'
    x = wm.cell(r, 13, m.get('amura') or 's/d'); x.font = N; x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='center')
    x = wm.cell(r, 14, m['nota']); x.font = N; x.fill = fl; x.border = bd
    for ci, (val, nd) in enumerate(((m.get('vmin'), 1), (m.get('dur'), 0), (m.get('radio'), 0), (m.get('barlo'), 0), (m.get('t_rec'), 0)), 15):
        x = wm.cell(r, ci, round(val, nd) if val is not None else None); x.font = N; x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='center')
        x.number_format = '0.0' if nd else ('+0;-0;0' if ci == 18 else '0')
    if not WS:
        x = wm.cell(r, 20, 's/d' if m.get('planeo') is None else ('Sí' if m['planeo'] else 'No')); x.font = N; x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='center')
    x = wm.cell(r, 10, f'=IF(OR(H{r}="",I{r}="",H{r}=0),"s/d",(I{r}-H{r})/H{r})'); x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='center')
    x.number_format = '+0.0%;[Red]-0.0%;0.0%'; x.font = N
for col, w in zip('ABCDEFGHIJKLMNOPQRST', [28, 14, 12, 16, 16, 12, 12, 18, 18, 20, 20, 20, 16, 26, 16, 14, 14, 20, 20, 16]): wm.column_dimensions[col].width = w
wm.freeze_panes = 'A5'
wr = wb.create_sheet('Resumen', 0); wr.sheet_view.showGridLines = False
wr['B2'] = f'Resumen del recorrido — {A.nombre} ({FECHA})' if A.nombre else f'Resumen del recorrido — {DISC} ({FECHA})'; wr['B2'].font = Font(name=F, bold=True, size=14)
last = max(5, 4+len(M))
cnt = lambda ty, rs: f'=COUNTIFS(Maniobras!B5:B{last},"{ty}",Maniobras!C5:C{last},"{rs}")'
L_PLAN = 'Tiempo navegando, >4 nudos (min)' if WS else 'Tiempo total de planeo, >7 nudos (min)'
def _r(x, nd): return 's/d' if x is None else round(x, nd)
def _mdx(ty_, k, nd):
    xs = sorted(m[k] for m in M if m['tipo'] == ty_ and m['resultado'] == 'Completa' and m.get(k) is not None)
    if not xs: return 's/d'
    q = len(xs)//2; return round(xs[q] if len(xs) % 2 else (xs[q-1]+xs[q])/2, nd)
rows = [*([('Nombre de la sesión', A.nombre, None)] if A.nombre else []),
        ('Disciplina', DISC, None),
        *([('Lugar', A.lugar, None)] if A.lugar else []),
        *([('Intensidad del viento (kn)', A.viento_kn, '0.0')] if A.viento_kn is not None else []),
        *([('Comentario', A.comentario, None)] if A.comentario else []),
        ('Origen del archivo', ORIGEN_TXT, None),
        ('Dirección del viento (desde)', VIENTO, None), ('Distancia total recorrida (km)', f'=Track!E{LR}/1000', '0.00'),
        ('Tiempo total del recorrido (min)', f'=SUM(Track!F3:F{LR})/60', '0.0'), (L_PLAN, f'=SUM(Track!H3:H{LR})/60', '0.0'),
        ('% del tiempo navegando (más de 4 nudos)' if WS else '% del tiempo planeando', '={plan}/{tiempo}', '0.0%'),
        (('Velocidad media navegando, >4 nudos (kn)' if WS else 'Velocidad media de navegación en planeo, >7 nudos (kn)'), f'=IF(SUM(Track!H3:H{LR})=0,"s/d",SUM(Track!J3:J{LR})/SUM(Track!H3:H{LR}))', '0.00'),
        ('Velocidad máxima en un tramo de 20 m (kn)', round(VM20, 2), '0.00'),
        ('Hora de la velocidad máxima (20 m)', hora(t[VM20a]), None),
        ('Viradas completas (sin caída)', cnt('Virada', 'Completa'), None), ('Viradas fallidas (con caída)', cnt('Virada', 'Fallida'), None),
        ('% de éxito en viradas', '=IF({vc}+{vf}=0,"s/d",{vc}/({vc}+{vf}))', '0.0%'), ('Trasluchadas completas (sin caída)', cnt('Trasluchada', 'Completa'), None),
        ('Trasluchadas fallidas (con caída)', cnt('Trasluchada', 'Fallida'), None), ('% de éxito en trasluchadas', '=IF({tc}+{tf}=0,"s/d",{tc}/({tc}+{tf}))', '0.0%'),
        *[x for ty_, pl_ in (('Trasluchada', 'trasluchadas'), ('Virada', 'viradas')) for x in (
            (f'Velocidad promedio de entrada a {pl_} completas (kn)', f'=IFERROR(AVERAGEIFS(Maniobras!H5:H{last},Maniobras!B5:B{last},"{ty_}",Maniobras!C5:C{last},"Completa"),"s/d")', '0.00'),
            (f'Velocidad promedio de salida de {pl_} completas (kn)', f'=IFERROR(AVERAGEIFS(Maniobras!I5:I{last},Maniobras!B5:B{last},"{ty_}",Maniobras!C5:C{last},"Completa"),"s/d")', '0.00'),
            (f'Variación promedio salida vs entrada, {pl_} completas (%)', f'=IFERROR(AVERAGEIFS(Maniobras!J5:J{last},Maniobras!B5:B{last},"{ty_}",Maniobras!C5:C{last},"Completa"),"s/d")', '+0.0%;[Red]-0.0%;0.0%'))],
        *[x for ty_, pl_ in (('Trasluchada', 'trasluchadas'), ('Virada', 'viradas')) for x in (
            (f'Velocidad mínima en el giro, {pl_} completas (mediana, kn)', _mdx(ty_, 'vmin', 2), '0.0'),
            (f'Duración del giro, {pl_} completas (mediana, s)', _mdx(ty_, 'dur', 0), '0'),
            (f'Radio del giro, {pl_} completas (mediana, m)', _mdx(ty_, 'radio', 0), '0'),
            (f'Metros contra el viento en el giro, {pl_} completas (mediana, m)', _mdx(ty_, 'barlo', 0), '+0;-0;0'),
            (f'Tiempo para recuperar la velocidad, {pl_} completas (mediana, s)', _mdx(ty_, 't_rec', 0), '0'),
            *([] if WS else [(f'Maniobras sin bajar de 7 kn (en planeo), {pl_}', sum(1 for m in M if m['tipo'] == ty_ and m.get('planeo')), None)]))],
        *[x for ld in ('babor', 'estribor') for x in (
            (f'Ángulo de ceñida, viento por {ld} (mediana, °)', _r(angulos[ld]['cenida'], 0), '0"°"'),
            (f'Ángulo en el largo, viento por {ld} (mediana, °)', _r(angulos[ld]['largo'], 0), '0"°"'),
            (f'VMG medio contra el viento, viento por {ld} (kn)', _r(angulos[ld]['vmg_up'], 2), '0.00'),
            (f'VMG medio a favor del viento, viento por {ld} (kn)', _r(angulos[ld]['vmg_dn'], 2), '0.00'))],
        ('Mejor VMG contra el viento, sostenido 10 s (kn)', _r(VMGU, 2), '0.00'),
        ('Mejor VMG a favor del viento, sostenido 10 s (kn)', _r(VMGD, 2), '0.00'),
        ('Cortes de señal GPS (cantidad)', N_CORTES, None),
        ('Tiempo total sin señal (min)', round(T_SIN/60, 2), '0.0'),
        (f'Puntos descartados por precisión (> {MAXACC:g} m)', n_acc, None)]
if ACC_OK:
    _sc = sum(e_['resultado'] == 'Completo' for e_ in SALTOS); _sf = len(SALTOS) - _sc
    rows += [(f'Saltos (vuelo de {SALTO_MIN:g} s o más y {A.salto_h_min:g} m o más)', len(SALTOS), None),
             ('Saltos completos (siguen navegando)', _sc, None), ('Saltos fallidos (con caída)', _sf, None),
             ('% de éxito en saltos', (_sc / len(SALTOS)) if SALTOS else 's/d', '0.0%'),
             ('Salto más alto (m)', round(max(e_['altura'] for e_ in SALTOS), 2) if SALTOS else 's/d', '0.00'),
             ('Hora del salto más alto', hora(max(SALTOS, key=lambda e_: e_['altura'])['t']) if SALTOS else 's/d', None)]
else:
    rows += [('Saltos', 'sin datos de acelerómetro', None)]
_ref = {}
for i, (l, vv, f) in enumerate(rows, 4): _ref[l] = f'C{i}'
_k = {'plan': _ref[L_PLAN], 'tiempo': _ref['Tiempo total del recorrido (min)'],
      'vc': _ref['Viradas completas (sin caída)'], 'vf': _ref['Viradas fallidas (con caída)'],
      'tc': _ref['Trasluchadas completas (sin caída)'], 'tf': _ref['Trasluchadas fallidas (con caída)']}
rows = [(l, vv.format(**_k) if isinstance(vv, str) and vv.startswith('=') and '{' in vv and 'Track!' not in vv and 'Maniobras!' not in vv else vv, f) for l, vv, f in rows]
_EX = wf_textos.resumen(WS)
wr.cell(3, 2, 'Dato').font = HFo; wr.cell(3, 2).fill = HF; wr.cell(3, 3, 'Valor').font = HFo; wr.cell(3, 3).fill = HF
wr.cell(3, 4, 'Qué es y para qué sirve').font = HFo; wr.cell(3, 4).fill = HF
for i, (l, vv, f) in enumerate(rows, 4):
    wr.cell(i, 2, l).font = B; x = wr.cell(i, 3, vv); x.font = N
    if f: x.number_format = f
    x = wr.cell(i, 4, wf_textos.buscar(_EX, l)); x.font = Font(name=F, size=9, color='555555'); x.alignment = Alignment(wrap_text=True, vertical='top')
    wr.cell(i, 2).alignment = Alignment(wrap_text=True, vertical='top'); wr.cell(i, 3).alignment = Alignment(vertical='top', horizontal='right')
    wr.row_dimensions[i].height = max(15, 12.5 * (1 + len(wr.cell(i, 4).value or '') // 95))
wr.column_dimensions['B'].width = 46; wr.column_dimensions['C'].width = 20; wr.column_dimensions['D'].width = 100
wr.freeze_panes = 'A4'
# hoja Rumbos: tiempo y velocidad por rumbo respecto al viento, y por amura
wrb = wb.create_sheet('Rumbos', 2); wrb.sheet_view.showGridLines = False
wrb['A1'] = f'Navegación por rumbo respecto al viento — {DISC} {FECHA} (viento desde {VIENTO})'; wrb['A1'].font = Font(name=F, bold=True, size=14)
wrb['A2'] = wf_textos.buscar(wf_textos.rumbos(WS), 'Rumbo'); wrb.merge_cells('A2:H2'); wrb['A2'].font = Font(name=F, italic=True, size=9, color='555555')
wrb['A2'].alignment = Alignment(wrap_text=True, vertical='top'); wrb.row_dimensions[2].height = 40
for ci, h in enumerate(['Rumbo', 'Grados al viento', 'Tiempo (min)', '% del tiempo medido', 'Vel. media (kn)', 'Vel. máx. (kn)', 'Vel. media viento por babor (kn)', 'Vel. media viento por estribor (kn)'], 1):
    x = wrb.cell(4, ci, h); x.font = HFo; x.fill = HF; x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
wrb.row_dimensions[4].height = 30
for r, q in enumerate(rumbos, 5):
    for ci, (val, fm) in enumerate(((q['rumbo'], None), (f"{q['desde']} a {q['hasta']}°", None), (_r(q['min'], 1), '0.0'), (q['pct'] if q['pct'] is not None else 's/d', '0.0%'),
                                     (_r(q['v_media'], 2), '0.00'), (_r(q['v_max'], 1), '0.0'), (_r(q['v_babor'], 2), '0.00'), (_r(q['v_estribor'], 2), '0.00')), 1):
        x = wrb.cell(r, ci, val); x.font = B if ci == 1 else N; x.border = bd; x.alignment = Alignment(horizontal='left' if ci == 1 else 'center')
        if fm: x.number_format = fm
r0 = 5 + len(rumbos) + 1
for k, (l, txt) in enumerate(wf_textos.rumbos(WS)[1:]):
    wrb.cell(r0 + k, 1, l).font = B; x = wrb.cell(r0 + k, 2, txt); x.font = Font(name=F, size=9, color='555555')
    wrb.merge_cells(start_row=r0 + k, start_column=2, end_row=r0 + k, end_column=8); x.alignment = Alignment(wrap_text=True, vertical='top'); wrb.row_dimensions[r0 + k].height = 28
for col, w in zip('ABCDEFGH', [14, 14, 12, 14, 14, 12, 18, 18]): wrb.column_dimensions[col].width = w
# hoja Glosario: qué es cada columna de la hoja Maniobras
wg = wb.create_sheet('Glosario'); wg.sheet_view.showGridLines = False
wg['A1'] = 'Glosario: qué es y para qué sirve cada columna de la hoja Maniobras'; wg['A1'].font = Font(name=F, bold=True, size=14)
for ci, h in enumerate(['Columna', 'Qué es y para qué sirve'], 1):
    x = wg.cell(3, ci, h); x.font = HFo; x.fill = HF
for r, (l, txt) in enumerate(wf_textos.maniobras(WS), 4):
    wg.cell(r, 1, l).font = B; x = wg.cell(r, 2, txt); x.font = N; x.alignment = Alignment(wrap_text=True, vertical='top')
    wg.cell(r, 1).alignment = Alignment(vertical='top'); wg.row_dimensions[r].height = max(15, 13 * (1 + len(txt) // 110))
wg.column_dimensions['A'].width = 22; wg.column_dimensions['B'].width = 120
if ACC_OK:
    wsx = wb.create_sheet('Saltos', 2)
    for ci, h in enumerate(['Nombre', 'Resultado', 'Hora local', 'Tiempo en vuelo (s)', 'Altura máxima estimada (m)', 'Distancia en vuelo (m)', 'Velocidad al despegar (kn)', 'Velocidad después (kn)', 'Impacto al aterrizar (g)', 'Latitud', 'Longitud', 'Observación'], 1):
        x = wsx.cell(1, ci, h); x.font = HFo; x.fill = HF; x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for r, e_ in enumerate(SALTOS, 2):
        flx = PatternFill('solid', fgColor='DFF9FF' if e_['resultado'] == 'Completo' else 'FFD6EC')
        for ci, val in enumerate([e_['nombre'], e_['resultado'], hora(e_['t']), round(e_['aire'], 2), round(e_['altura'], 2), round(e_['dist'], 1), round(e_['v_in'], 1),
                                  round(e_['v_out'], 1) if e_['v_out'] is not None else None, round(e_['impacto_g'], 1), round(e_['lat'], 6), round(e_['lon'], 6), e_['nota']], 1):
            x = wsx.cell(r, ci, val); x.font = N; x.fill = flx
    for col, w in zip('ABCDEFGHIJKL', [24, 12, 12, 14, 16, 16, 16, 18, 18, 12, 12, 30]): wsx.column_dimensions[col].width = w
    wsx.row_dimensions[1].height = 30
xlsx_path = os.path.join(A.outdir, f'track_{A.disciplina}_{FECHA}_maniobras.xlsx'); wb.save(xlsx_path)
print("KML:", kml_path); print("XLSX:", xlsx_path)

# 9) JSON opcional con todos los resultados (para el PDF de la app)
if A.json:
    def _prom(L_, k):
        x_ = [m[k] for m in L_ if m.get(k) is not None]
        return sum(x_)/len(x_) if x_ else None
    def _mediana(xs):
        xs = sorted(x for x in xs if x is not None)
        if not xs: return None
        k = len(xs)//2
        return xs[k] if len(xs) % 2 else (xs[k-1]+xs[k])/2
    def _var(L_):
        x_ = [(m['v_out']-m['v_in'])/m['v_in'] for m in L_ if m['v_out'] is not None and m['v_in']]
        return sum(x_)/len(x_) if x_ else None
    cnts = {f"{ty_}_{rs_}": sum(1 for m in M if m['tipo'] == ty_ and m['resultado'] == rs_)
            for ty_ in ('Virada', 'Trasluchada') for rs_ in ('Completa', 'Fallida')}
    por_tipo = {}
    for ty_ in ('Trasluchada', 'Virada'):
        L_ = [m for m in M if m['tipo'] == ty_ and m['resultado'] == 'Completa']    # velocidades y variación: solo completas
        c_, f_ = cnts[f'{ty_}_Completa'], cnts[f'{ty_}_Fallida']
        Lf_ = [m for m in M if m['tipo'] == ty_ and m['resultado'] == 'Fallida']
        Pl_ = [m for m in M if m['tipo'] == ty_ and m.get('planeo') is not None]
        por_tipo[ty_] = {'completas': c_, 'fallidas': f_, 'exito': (c_/(c_+f_)) if c_+f_ else None,
                         'v_in': _prom(L_, 'v_in'), 'v_out': _prom(L_, 'v_out'), 'variacion': _var(L_),
                         'en_planeo': sum(1 for m in Pl_ if m['planeo']), 'en_planeo_pct': (sum(1 for m in Pl_ if m['planeo'])/len(Pl_)) if Pl_ else None,
                         **{f'{k}_med': _mediana([m.get(k) for m in L_]) for k in ('vmin', 'dur', 'radio', 'barlo', 't_rec')},
                         **{f'{k}_med_f': _mediana([m.get(k) for m in Lf_]) for k in ('vmin', 'dur', 'radio', 'barlo')}}
    paso = max(1, n // 5000)
    res = {
        'disciplina': A.disciplina, 'v_nav': V_NAV, 'v_ent_min': V_ENT_MIN,
        'nav_min': nav4/60, 'vel_media_nav': navv4,
        'rumbos': rumbos, 'angulos': angulos, 'nav_medida_min': TNAV/60,
        'vmg_up': VMGU, 'vmg_up_hora': hora(VMGU_T) if VMGU_T is not None else None,
        'vmg_dn': VMGD, 'vmg_dn_hora': hora(VMGD_T) if VMGD_T is not None else None,
        'fecha': FECHA, 'origen': ORIGEN_TXT, 'viento': WIND_FROM, 'secciones': NS,
        'nombre': A.nombre, 'lugar': A.lugar, 'viento_kn': A.viento_kn, 'comentario': A.comentario,
        'hora_inicio': hora(t[0]), 'hora_fin': hora(t[-1]),
        'distancia_km': cd[-1]/1000, 'tiempo_min': tt/60, 'planeo_min': plan/60,
        'planeo_pct': (plan/tt) if tt else 0, 'vel_media_planeo': navv,
        'vmax20': VM20, 'vmax20_hora': hora(t[VM20a]), 'vmax20_lat': lat[VM20a], 'vmax20_lon': lon[VM20a], 'vmax20_cd': cd[VM20a],
        'cortes': N_CORTES, 'sin_senal_min': T_SIN/60, 'descartados_precision': n_acc, 'max_acc': MAXACC,
        'excluidos': [[hora(a_), hora(b_)] for a_, b_ in EXC],
        'por_tipo': por_tipo,
        'maniobras': [{'nombre': m['nombre'], 'tipo': m['tipo'], 'resultado': m['resultado'],
                       'transcurrido': f"{int((m['t']-T0)//60):02d}:{int((m['t']-T0)%60):02d}", 'hora': hora(m['t']),
                       'lat': m['lat'], 'lon': m['lon'], 'v_in': m['v_in'], 'v_out': m['v_out'],
                       'variacion': ((m['v_out']-m['v_in'])/m['v_in']) if m['v_out'] is not None and m['v_in'] else None,
                       'ang_in': m['ang_in'], 'ang_out': m['ang_out'], 'amura': m.get('amura'), 't_rel': m['t']-T0,
                       'dur': m.get('dur'), 'radio': m.get('radio'), 'vmin': m.get('vmin'), 'barlo': m.get('barlo'),
                       't_rec': m.get('t_rec'), 'planeo': m.get('planeo'),
                       'nota': m['nota'], 'cd': cd[min(range(n), key=lambda q: abs(t[q]-m['t']))]} for m in M],
        'acc': ACC_OK, 'salto_min': SALTO_MIN, 'salto_h_min': A.salto_h_min,
        'saltos': [{'nombre': e_['nombre'], 'hora': hora(e_['t']), 'aire': e_['aire'], 'altura': e_['altura'], 'dist': e_['dist'], 'v_in': e_['v_in'],
                    'v_out': e_['v_out'], 'impacto_g': e_['impacto_g'], 'lat': e_['lat'], 'lon': e_['lon'], 'cd': e_['cd'],
                    'resultado': e_['resultado'], 'nota': e_['nota']} for e_ in SALTOS],
        'track': [[round(lat[i], 7), round(lon[i], 7), round(v[i], 2), seg[i], round(cd[i], 1), round(t[i], 1)] for i in range(0, n, paso)],
        'dist_total_m': cd[-1], 'epoch': EP, 'utc': UTC,
        'kml': os.path.basename(kml_path), 'xlsx': os.path.basename(xlsx_path),
    }
    with open(A.json, 'w', encoding='utf-8') as fj: json.dump(res, fj, ensure_ascii=False)
    print("JSON:", A.json)
