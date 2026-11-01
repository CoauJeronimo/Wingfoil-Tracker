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
ap.add_argument('--salto-min', type=float, default=0.5, help='altura mínima (m) para informar un salto (por defecto 0.5)')
A = ap.parse_args()
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
if 'wingfoiltracker' in appv.lower().replace(' ', ''): ORIGEN = 'Wingfoil Tracker'
elif meta: ORIGEN = 'Sensor Logger'
else: ORIGEN = 'No identificado (sin Metadata.csv)'
if appv: ORIGEN_TXT = f"{ORIGEN} ({appv})"
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

# 7) UNIÓN, deduplicado (<15 s), velocidades, COMPLETA/FALLIDA, filtro de entrada >= 6 kn
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
fin = []
for m in dd:
    i = min(range(n), key=lambda q: abs(t[q]-m['t'])); c0 = cd[i]; SG = seg[i]
    vi = avg(c0-40, c0); vo = avg(c0, c0+40)
    if vi is None or vi < 6: continue          # no estaba foileando
    fin_seg = max(cd[q] for q in range(i, n) if seg[q] == SG)
    cayo_agua = SG in corte and fin_seg < c0 + 40          # la señal se corta (teléfono bajo el agua) antes de 40 m
    m.update({'resultado': 'Fallida' if (blanco(c0, c0+40) or cayo_agua) else 'Completa', 'v_in': vi, 'v_out': vo,
              'nota': 'corte de señal tras el giro' if cayo_agua else ''}); fin.append(m)
c = {}
for m in fin:
    key = m['tipo']; c[key] = c.get(key, 0) + 1          # numeración consecutiva por tipo (completas y fallidas juntas)
    m['numero_grupo'] = c[key]; m['nombre'] = f"{m['tipo']} #{c[key]} ({m['resultado']})"
print(Counter((m['tipo'], m['resultado']) for m in fin))
for ty_ in ('Trasluchada', 'Virada'):
    L_ = [m for m in fin if m['tipo'] == ty_]
    if not L_: print(f"{ty_}s: sin maniobras"); continue
    vi_ = [m['v_in'] for m in L_]; vo_ = [m['v_out'] for m in L_ if m['v_out'] is not None]
    va_ = [(m['v_out']-m['v_in'])/m['v_in'] for m in L_ if m['v_out'] is not None and m['v_in']]
    print(f"{ty_}s ({len(L_)}): entrada media {sum(vi_)/len(vi_):.2f} kn | salida media {sum(vo_)/len(vo_):.2f} kn | variación media {sum(va_)/len(va_)*100:+.1f}%")
M = fin

# 8) SALTOS con el acelerómetro (TotalAcceleration.csv, opcional: Sensor Logger o Wingfoil Tracker >= 1.5)
#    En el aire el teléfono (en el pecho) queda casi en caída libre: |a| muy por debajo de 1 g.
#    Tiempo en el aire t -> altura h = (g - a_media) * t² / 8  (a_media = tirón del ala que queda durante el vuelo).
#    Salto = se sigue navegando después (>= 6 kn de media entre 1 y 5 s después, sin corte de señal).
#    Si después se para o se corta la señal (teléfono al agua), es una CAÍDA y no se cuenta como salto.
G = 9.81; A_LOW = 5.0; SALTO_MIN = A.salto_min
SALTOS = []; CAIDAS_AIRE = []; ACC_OK = False
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
        A_EDGE = (A_LOW + G) / 2; ext = int(0.15 * fs)
        for i0_, j0_ in runs:
            lim_ = i0_ - ext
            while i0_ > 0 and i0_ > lim_ and am[i0_ - 1] < A_EDGE: i0_ -= 1      # bordes con la señal sin suavizar
            lim_ = j0_ + ext
            while j0_ < NA and j0_ < lim_ and am[j0_] < A_EDGE: j0_ += 1
            dur = ta[j0_ - 1] - ta[i0_]
            if dur < 0.2: continue
            a_med = sum(am[i0_:j0_]) / (j0_ - i0_)
            h_ = max(0.0, G - a_med) * dur * dur / 8
            if h_ < SALTO_MIN: continue
            ts_ = ta[i0_]; te_ = ta[j0_ - 1]
            if ts_ < t[0] or ts_ > t[-1] or any(a_ <= ts_ <= b_ for a_, b_ in EXC): continue
            k_ = bisect.bisect_left(t, ts_); k_ = min(max(k_, 0), n - 1)
            if k_ > 0 and abs(t[k_-1] - ts_) < abs(t[k_] - ts_): k_ -= 1
            if abs(t[k_] - ts_) > 3: continue                         # sin GPS cerca
            v_in = v[k_]
            if v_in < 7: continue                                     # solo navegando en planeo
            imp = max(am[j0_:min(NA, j0_ + int(0.6 * fs) + 1)] or [0])
            desp = [i for i in range(k_, n) if te_ + 1 <= t[i] <= te_ + 5 and seg[i] == seg[k_]]
            corte_ = any(t[i] - t[i-1] > 3 or seg[i] != seg[i-1] for i in range(k_ + 1, n) if t[i-1] <= te_ + 5)
            v_out = sum(v[i] for i in desp) / len(desp) if desp else None
            ev = {'t': ts_, 'aire': dur, 'altura': h_, 'v_in': v_in, 'v_out': v_out, 'impacto_g': imp / G,
                  'lat': lat[k_], 'lon': lon[k_], 'cd': cd[k_]}
            (SALTOS if (v_out is not None and v_out >= 6 and not corte_) else CAIDAS_AIRE).append(ev)
        for i_, e_ in enumerate(SALTOS, 1): e_['nombre'] = f"Salto #{i_}"
    print(f"Saltos (>= {SALTO_MIN:g} m): {len(SALTOS)}" + (f" | más alto {max(e_['altura'] for e_ in SALTOS):.2f} m" if SALTOS else '') +
          f" | caídas desde el aire (no cuentan): {len(CAIDAS_AIRE)}")
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
k_ = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2">', '<Document>', f'<name>Track Wingfoil {FECHA}</name>']
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
        h = hora(m['t']); d = f"Hora: {h}<br/>Vel. entrada (40m): {m['v_in']:.1f} kn | Vel. salida (40m): {('%.1f' % m['v_out']) if m['v_out'] is not None else 's/d'} kn" + (f"<br/>Nota: {m['nota']}" if m['nota'] else '')
        k_.append(f'<Placemark><name>{esc(m["tipo"])} #{m["numero_grupo"]} — {h} ({m["resultado"]})</name><description><![CDATA[{d}]]></description><styleUrl>#{ic}</styleUrl><Point><coordinates>{m["lon"]:.7f},{m["lat"]:.7f},0</coordinates></Point></Placemark>')
    k_.append('</Folder>')
k_.append('</Folder>')
if SALTOS:
    k_.append('<Style id="salto"><IconStyle><scale>1.2</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-blank.png</href></Icon></IconStyle></Style>')
    k_.append(f'<Folder><name>Saltos (>= {SALTO_MIN:g} m) ({len(SALTOS)})</name>')
    for e_ in SALTOS:
        d_ = f"Hora: {hora(e_['t'])}<br/>Tiempo en el aire: {e_['aire']:.2f} s<br/>Altura estimada: {e_['altura']:.2f} m<br/>Velocidad: {e_['v_in']:.1f} kn"
        k_.append(f'<Placemark><name>{e_["nombre"]} — {e_["altura"]:.1f} m — {hora(e_["t"])}</name><description><![CDATA[{d_}]]></description><styleUrl>#salto</styleUrl><Point><coordinates>{e_["lon"]:.7f},{e_["lat"]:.7f},0</coordinates></Point></Placemark>')
    k_.append('</Folder>')
k_.append('<Style id="vmax"><IconStyle><scale>1.3</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/purple-stars.png</href></Icon></IconStyle></Style>')
k_.append(f'<Placemark><name>Velocidad máxima 20 m: {VM20:.1f} kn — {hora(t[VM20a])}</name><description><![CDATA[Media de la velocidad GPS en el tramo de 20 m de mayor velocidad ({hora(t[VM20a])} a {hora(t[VM20b])}).]]></description><styleUrl>#vmax</styleUrl><Point><coordinates>{lon[VM20a]:.7f},{lat[VM20a]:.7f},0</coordinates></Point></Placemark>')
k_ += ['</Document>', '</kml>']
kml_path = os.path.join(A.outdir, f'track_wingfoil_{FECHA}_maniobras.kml'); open(kml_path, 'w', encoding='utf-8').write("\n".join(k_))

F = 'Arial'; HF = PatternFill('solid', fgColor='1F4E78'); HFo = Font(name=F, bold=True, color='FFFFFF', size=10); N = Font(name=F, size=10); B = Font(name=F, bold=True, size=10)
bd = Border(*(Side(style='thin', color='CCCCCC'),)*4)
fills = {('Virada', 'Completa'): 'C6EFCE', ('Virada', 'Fallida'): 'FFC7CE', ('Trasluchada', 'Completa'): 'DDEBF7', ('Trasluchada', 'Fallida'): 'FCE4D6'}
wb = Workbook(); wt = wb.active; wt.title = 'Track'
for ci, h in enumerate(['t_seg', 'lat', 'lon', 'velocidad_kn', 'dist_acum_m', 'dt_seg', 'vel_media_seg_kn', 'dt_planeo_seg', 'segmento', 'dt_x_vel_planeo'], 1):
    x = wt.cell(1, ci, h); x.font = HFo; x.fill = HF
for r, p in enumerate(track, 2):
    for ci, val in enumerate([round(p['t'], 3), round(p['lat'], 7), round(p['lon'], 7), round(p['speed_kn'], 3), round(p['cumdist'], 2)], 1): wt.cell(r, ci, val).font = N
    wt.cell(r, 9, p['seg'] + 1).font = N
    if r > 2:
        wt.cell(r, 6, f"=IF(I{r}=I{r-1},A{r}-A{r-1},0)"); wt.cell(r, 7, f"=AVERAGE(D{r-1}:D{r})"); wt.cell(r, 8, f"=IF(G{r}>7,F{r},0)")
        wt.cell(r, 10, f"=H{r}*G{r}")
LR = len(track)+1; wt.freeze_panes = 'A2'
wm = wb.create_sheet('Maniobras', 0); wm.sheet_view.showGridLines = False
wm['A1'] = f'Track Wingfoil {FECHA} — Viradas y Trasluchadas (Completa vs Fallida)'; wm['A1'].font = Font(name=F, bold=True, size=14)
wm['A2'] = (f'Viento desde {VIENTO}. "Completa" = sin caída SOSTENIDA (2+ muestras seguidas) bajo 4 nudos en los 40m posteriores al giro. "Fallida" = caída sostenida bajo 4 nudos en esos 40m. Si la señal GPS se corta (teléfono bajo el agua) antes de completar esos 40m, también es Fallida. Se excluye toda maniobra con velocidad de entrada (40m previos) < 6 nudos y los giros que no cruzan limpiamente ningún eje.')
wm.merge_cells('A2:K2'); wm.row_dimensions[2].height = 40; wm['A2'].font = Font(name=F, italic=True, size=9, color='555555'); wm['A2'].alignment = Alignment(wrap_text=True, vertical='top')
for ci, h in enumerate(['Nombre (igual que en el KML)', 'Tipo', 'Resultado', 'Tiempo transcurrido', 'Hora local', 'Latitud', 'Longitud', 'Vel. entrada 40m (kn)', 'Vel. salida 40m (kn)', 'Variación salida vs entrada (%)', 'Observación'], 1):
    x = wm.cell(4, ci, h); x.font = HFo; x.fill = HF; x.border = bd; x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
wm.row_dimensions[4].height = 30
for r, m in enumerate(M, 5):
    tr = m['t']-T0; fl = PatternFill('solid', fgColor=fills[(m['tipo'], m['resultado'])])
    vals = [m['nombre'], m['tipo'], m['resultado'], f"{int(tr//60):02d}:{int(tr%60):02d}", hora(m['t']), round(m['lat'], 6), round(m['lon'], 6), round(m['v_in'], 2), round(m['v_out'], 2) if m['v_out'] is not None else None]
    for ci, val in enumerate(vals, 1):
        x = wm.cell(r, ci, val); x.font = N; x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='left' if ci == 1 else 'center')
    x = wm.cell(r, 11, m['nota']); x.font = N; x.fill = fl; x.border = bd
    x = wm.cell(r, 10, f'=IF(OR(H{r}="",I{r}="",H{r}=0),"s/d",(I{r}-H{r})/H{r})'); x.fill = fl; x.border = bd; x.alignment = Alignment(horizontal='center')
    x.number_format = '+0.0%;[Red]-0.0%;0.0%'; x.font = N
for col, w in zip('ABCDEFGHIJK', [28, 14, 12, 16, 16, 12, 12, 18, 18, 20, 26]): wm.column_dimensions[col].width = w
wm.freeze_panes = 'A5'
wr = wb.create_sheet('Resumen', 0); wr.sheet_view.showGridLines = False
wr['B2'] = f'Resumen del recorrido — Wingfoil ({FECHA})'; wr['B2'].font = Font(name=F, bold=True, size=14)
last = max(5, 4+len(M))
cnt = lambda ty, rs: f'=COUNTIFS(Maniobras!B5:B{last},"{ty}",Maniobras!C5:C{last},"{rs}")'
rows = [('Origen del archivo', ORIGEN_TXT, None),
        ('Dirección del viento (desde)', VIENTO, None), ('Distancia total recorrida (km)', f'=Track!E{LR}/1000', '0.00'),
        ('Tiempo total del recorrido (min)', f'=SUM(Track!F3:F{LR})/60', '0.0'), ('Tiempo total de planeo, >7 nudos (min)', f'=SUM(Track!H3:H{LR})/60', '0.0'),
        ('% del tiempo planeando', '={plan}/{tiempo}', '0.0%'),
        ('Velocidad media de navegación en planeo, >7 nudos (kn)', f'=IF(SUM(Track!H3:H{LR})=0,"s/d",SUM(Track!J3:J{LR})/SUM(Track!H3:H{LR}))', '0.00'),
        ('Velocidad máxima en un tramo de 20 m (kn)', round(VM20, 2), '0.00'),
        ('Hora de la velocidad máxima (20 m)', hora(t[VM20a]), None),
        ('Viradas completas (sin caída)', cnt('Virada', 'Completa'), None), ('Viradas fallidas (con caída)', cnt('Virada', 'Fallida'), None),
        ('% de éxito en viradas', '=IF({vc}+{vf}=0,"s/d",{vc}/({vc}+{vf}))', '0.0%'), ('Trasluchadas completas (sin caída)', cnt('Trasluchada', 'Completa'), None),
        ('Trasluchadas fallidas (con caída)', cnt('Trasluchada', 'Fallida'), None), ('% de éxito en trasluchadas', '=IF({tc}+{tf}=0,"s/d",{tc}/({tc}+{tf}))', '0.0%'),
        *[x for ty_, pl_ in (('Trasluchada', 'trasluchadas'), ('Virada', 'viradas')) for x in (
            (f'Velocidad promedio de entrada a {pl_} (kn)', f'=IFERROR(AVERAGEIFS(Maniobras!H5:H{last},Maniobras!B5:B{last},"{ty_}"),"s/d")', '0.00'),
            (f'Velocidad promedio de salida de {pl_} (kn)', f'=IFERROR(AVERAGEIFS(Maniobras!I5:I{last},Maniobras!B5:B{last},"{ty_}"),"s/d")', '0.00'),
            (f'Variación promedio salida vs entrada, {pl_} (%)', f'=IFERROR(AVERAGEIFS(Maniobras!J5:J{last},Maniobras!B5:B{last},"{ty_}"),"s/d")', '+0.0%;[Red]-0.0%;0.0%'))],
        ('Cortes de señal GPS (cantidad)', N_CORTES, None),
        ('Tiempo total sin señal (min)', round(T_SIN/60, 2), '0.0'),
        (f'Puntos descartados por precisión (> {MAXACC:g} m)', n_acc, None)]
if ACC_OK:
    rows += [(f'Saltos de {SALTO_MIN:g} m o más (cantidad)', len(SALTOS), None),
             ('Salto más alto (m)', round(max(e_['altura'] for e_ in SALTOS), 2) if SALTOS else 's/d', '0.00'),
             ('Hora del salto más alto', hora(max(SALTOS, key=lambda e_: e_['altura'])['t']) if SALTOS else 's/d', None)]
else:
    rows += [('Saltos', 'sin datos de acelerómetro', None)]
_ref = {}
for i, (l, vv, f) in enumerate(rows, 4): _ref[l] = f'C{i}'
_k = {'plan': _ref['Tiempo total de planeo, >7 nudos (min)'], 'tiempo': _ref['Tiempo total del recorrido (min)'],
      'vc': _ref['Viradas completas (sin caída)'], 'vf': _ref['Viradas fallidas (con caída)'],
      'tc': _ref['Trasluchadas completas (sin caída)'], 'tf': _ref['Trasluchadas fallidas (con caída)']}
rows = [(l, vv.format(**_k) if isinstance(vv, str) and vv.startswith('=') and '{' in vv and 'Track!' not in vv and 'Maniobras!' not in vv else vv, f) for l, vv, f in rows]
for i, (l, vv, f) in enumerate(rows, 4):
    wr.cell(i, 2, l).font = B; x = wr.cell(i, 3, vv); x.font = N
    if f: x.number_format = f
wr.column_dimensions['B'].width = 46; wr.column_dimensions['C'].width = 20
if ACC_OK:
    wsx = wb.create_sheet('Saltos', 2)
    for ci, h in enumerate(['Nombre (igual que en el KML)', 'Hora local', 'Tiempo en el aire (s)', 'Altura estimada (m)', 'Velocidad (kn)', 'Velocidad después (kn)', 'Impacto al aterrizar (g)', 'Latitud', 'Longitud'], 1):
        x = wsx.cell(1, ci, h); x.font = HFo; x.fill = HF; x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for r, e_ in enumerate(SALTOS, 2):
        for ci, val in enumerate([e_['nombre'], hora(e_['t']), round(e_['aire'], 2), round(e_['altura'], 2), round(e_['v_in'], 1),
                                  round(e_['v_out'], 1) if e_['v_out'] is not None else None, round(e_['impacto_g'], 1), round(e_['lat'], 6), round(e_['lon'], 6)], 1):
            wsx.cell(r, ci, val).font = N
    for col, w in zip('ABCDEFGHI', [28, 12, 16, 16, 14, 18, 18, 12, 12]): wsx.column_dimensions[col].width = w
    wsx.row_dimensions[1].height = 30
xlsx_path = os.path.join(A.outdir, f'track_wingfoil_{FECHA}_maniobras.xlsx'); wb.save(xlsx_path)
print("KML:", kml_path); print("XLSX:", xlsx_path)

# 9) JSON opcional con todos los resultados (para el PDF de la app)
if A.json:
    def _prom(L_, k):
        x_ = [m[k] for m in L_ if m.get(k) is not None]
        return sum(x_)/len(x_) if x_ else None
    def _var(L_):
        x_ = [(m['v_out']-m['v_in'])/m['v_in'] for m in L_ if m['v_out'] is not None and m['v_in']]
        return sum(x_)/len(x_) if x_ else None
    cnts = {f"{ty_}_{rs_}": sum(1 for m in M if m['tipo'] == ty_ and m['resultado'] == rs_)
            for ty_ in ('Virada', 'Trasluchada') for rs_ in ('Completa', 'Fallida')}
    por_tipo = {}
    for ty_ in ('Trasluchada', 'Virada'):
        L_ = [m for m in M if m['tipo'] == ty_]
        c_, f_ = cnts[f'{ty_}_Completa'], cnts[f'{ty_}_Fallida']
        por_tipo[ty_] = {'completas': c_, 'fallidas': f_, 'exito': (c_/(c_+f_)) if c_+f_ else None,
                         'v_in': _prom(L_, 'v_in'), 'v_out': _prom(L_, 'v_out'), 'variacion': _var(L_)}
    paso = max(1, n // 5000)
    res = {
        'fecha': FECHA, 'origen': ORIGEN_TXT, 'viento': WIND_FROM, 'secciones': NS,
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
                       'nota': m['nota'], 'cd': cd[min(range(n), key=lambda q: abs(t[q]-m['t']))]} for m in M],
        'acc': ACC_OK, 'salto_min': SALTO_MIN,
        'saltos': [{'nombre': e_['nombre'], 'hora': hora(e_['t']), 'aire': e_['aire'], 'altura': e_['altura'], 'v_in': e_['v_in'],
                    'v_out': e_['v_out'], 'impacto_g': e_['impacto_g'], 'lat': e_['lat'], 'lon': e_['lon'], 'cd': e_['cd']} for e_ in SALTOS],
        'caidas_aire': len(CAIDAS_AIRE),
        'track': [[round(lat[i], 7), round(lon[i], 7), round(v[i], 2), seg[i], round(cd[i], 1), round(t[i], 1)] for i in range(0, n, paso)],
        'dist_total_m': cd[-1], 'epoch': EP, 'utc': UTC,
        'kml': os.path.basename(kml_path), 'xlsx': os.path.basename(xlsx_path),
    }
    with open(A.json, 'w', encoding='utf-8') as fj: json.dump(res, fj, ensure_ascii=False)
    print("JSON:", A.json)
