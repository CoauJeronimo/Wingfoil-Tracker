"""Tramos a excluir: prepara el track para la pantalla de la app y detecta posibles salidas del agua.

Usa la misma limpieza que wingfoil_analisis.py (precisión, saltos > 35 kn, recorte de inicio y fin),
así las horas que se eligen en la pantalla son las mismas que usa el análisis.
"""
import csv, json, math, os, datetime

K = 1.9438444924406


def _hv(a, b, c, d):
    R = 6371000; p1, p2 = math.radians(a), math.radians(c); dp = p2 - p1; dl = math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def _f(r, k):
    x = (r.get(k) or '').strip()
    try:
        return float(x) if x else None
    except ValueError:
        return None


def puntos(session_dir, utc=-3.0):
    meta = {}
    mp = os.path.join(session_dir, 'Metadata.csv')
    if os.path.exists(mp):
        rows = list(csv.DictReader(open(mp, encoding='utf-8-sig')))
        if rows: meta = {(k or '').strip().lower(): (v or '').strip() for k, v in rows[0].items()}
    tracker = 'wingfoiltracker' in meta.get('appversion', '').lower().replace(' ', '')
    maxacc = 10.0 if tracker else 20.0
    gap = 5.0 if tracker else 0.0
    ep = float(meta.get('recording epoch time') or 0) / 1000.0
    raw = []
    for r in csv.DictReader(open(os.path.join(session_dir, 'Location.csv'), encoding='utf-8-sig')):
        la, lo, sp, t = _f(r, 'latitude'), _f(r, 'longitude'), _f(r, 'speed'), _f(r, 'seconds_elapsed')
        if t is None and _f(r, 'time') is not None and ep: t = _f(r, 'time')/1e9 - ep
        ac = _f(r, 'horizontalAccuracy')
        if None in (la, lo, sp, t): continue
        if ac is not None and ac > maxacc: continue
        raw.append((t, la, lo, sp*K, ac))
    raw.sort(key=lambda x: x[0])
    import wf_senal
    dud, _, _ = wf_senal.dudosos(raw, reenganche='gpx importado' not in meta.get('appversion', '').lower())
    raw = [x[:4] for x in raw]
    if not raw: return [], ep
    if 'gpx importado' in meta.get('appversion', '').lower() and len(raw) > 2:   # mismo criterio que el análisis
        dts = sorted(raw[k+1][0] - raw[k][0] for k in range(len(raw)-1) if raw[k+1][0] > raw[k][0])
        gap = max(5.0, 3 * dts[len(dts)//2]) if dts else 5.0
    cl = [raw[0]]
    for x in raw[1:]:
        dt = x[0] - cl[-1][0]
        if dt <= 0: continue
        if _hv(cl[-1][1], cl[-1][2], x[1], x[2]) / dt * K > 35: continue
        cl.append(x)
    i0 = next((i for i, c in enumerate(cl) if c[3] >= 4), None)
    if i0 is None: return [], ep
    i1 = next(i for i in range(len(cl)-1, -1, -1) if cl[i][3] > 4)
    cl = cl[i0:i1+1]
    seg = 0; out = []
    for k, c in enumerate(cl):
        if k and gap > 0 and c[0] - cl[k-1][0] > gap: seg += 1
        h = (datetime.datetime.fromtimestamp(ep + c[0], datetime.timezone.utc) + datetime.timedelta(hours=utc)).strftime('%H:%M:%S')
        out.append([round(c[0], 2), round(c[1], 7), round(c[2], 7), round(c[3], 2), seg, h, 1 if c[0] in dud else 0])
    return out, ep


def detectar(P, min_dur=180.0, v_media=3.0):
    """Posibles salidas del agua: varios minutos sin planear (< 7 kn) y casi quieto o caminando (media < 3 kn)."""
    runs = []; i = 0; n = len(P)
    while i < n:
        if P[i][3] < 5:
            j = i
            while j < n and P[j][3] < 7 and (j == i or P[j][0] - P[j-1][0] < 60): j += 1
            runs.append([i, j-1]); i = j
        else:
            i += 1
    merged = []                     # une tramos separados por menos de 60 s (un pico suelto del GPS)
    for a, b in runs:
        if merged and P[a][0] - P[merged[-1][1]][0] < 60: merged[-1][1] = b
        else: merged.append([a, b])
    res = []
    for a, b in merged:
        d = P[b][0] - P[a][0]
        if d < min_dur or a == 0 or b == n-1: continue
        vs = [p[3] for p in P[a:b+1]]
        vm = sum(vs)/len(vs)
        if vm >= v_media: continue
        res.append({'ini': P[a][5], 'fin': P[b][5], 'min': round(d/60, 1), 'v': round(vm, 1), 'marcar': d >= 300})
    return res


def preparar(session_dir):
    try:
        P, ep = puntos(session_dir)
        if len(P) < 2:
            return json.dumps({'ok': False, 'error': 'La sesión no tiene suficientes puntos GPS.'}, ensure_ascii=False)
        return json.dumps({'ok': True, 'puntos': P, 'detectados': detectar(P)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': f"{type(e).__name__}: {e}"}, ensure_ascii=False)
