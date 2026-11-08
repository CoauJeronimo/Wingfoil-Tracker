"""Importar un GPX como sesión guardada.

Crea una carpeta de sesión con Location.csv y Metadata.csv en el mismo formato que graba la app,
así la sesión se analiza, se renombra, se exporta y se borra igual que cualquier otra.
Metadata: appVersion 'GPX importado' (el análisis la reconoce como sesión importada).
"""
import json, math, os, re, datetime, shutil
import xml.etree.ElementTree as ET


def _hv(a, b, c, d):
    R = 6371000; p1, p2 = math.radians(a), math.radians(c); dp = p2 - p1; dl = math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def _t(s):
    s = s.strip().replace('Z', '+00:00')
    m = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$', s)
    if not m: return None
    base, frac, tz = m.group(1), m.group(2) or '', m.group(3) or '+00:00'
    d = datetime.datetime.fromisoformat(base + tz)
    return d.timestamp() + (float(frac) if frac else 0.0)


def _local(tag): return tag.rsplit('}', 1)[-1].lower()


def leer(path):
    root = ET.parse(path).getroot()
    creator = root.attrib.get('creator', '').strip()
    nombre = ''
    pts = []
    for el in root.iter():
        tg = _local(el.tag)
        if tg == 'name' and not nombre and (el.text or '').strip(): nombre = el.text.strip()
        if tg not in ('trkpt', 'rtept'): continue
        try:
            la = float(el.attrib['lat']); lo = float(el.attrib['lon'])
        except (KeyError, ValueError):
            continue
        tm = ele = sp = hd = None
        for ch in el.iter():
            c = _local(ch.tag); tx = (ch.text or '').strip()
            if not tx: continue
            try:
                if c == 'time': tm = _t(tx)
                elif c == 'ele': ele = float(tx)
                elif c == 'speed' and sp is None: sp = float(tx)       # m/s (GPX 1.0 o extensiones Garmin)
                elif c == 'hdop': hd = float(tx)
            except ValueError:
                pass
        if tm is None: continue
        pts.append([tm, la, lo, ele, sp, hd])
    pts.sort(key=lambda p: p[0])
    out = []
    for p in pts:                                   # puntos repetidos en el mismo instante: se queda el primero
        if out and p[0] - out[-1][0] <= 0: continue
        out.append(p)
    return out, nombre, creator


def importar(gpx_path, sessions_root, utc_offset_h=-3.0, archivo=''):
    try:
        P, nombre, creator = leer(gpx_path)
        if len(P) < 10:
            return json.dumps({'ok': False, 'error': 'El GPX no tiene puntos con hora suficientes para analizar (hacen falta latitud, longitud y hora en cada punto).'}, ensure_ascii=False)
        n = len(P)
        # velocidad: la del GPX si viene; si no, por posición: se suavizan las posiciones (promedio de ±3 s)
        # y se mide la cuerda de ±2 s. Probado contra la velocidad Doppler: error típico < 1 kn.
        con_vel = sum(1 for p in P if p[4] is not None) > n * 0.8
        T = [p[0] for p in P]
        kx = math.cos(math.radians(P[0][1])) * 111320.0; ky = 110574.0
        X = [p[2] * kx for p in P]; Y = [p[1] * ky for p in P]
        def win(i, k):
            a_, b_ = i, i
            while a_ > 0 and T[i] - T[a_-1] <= k: a_ -= 1
            while b_ < n-1 and T[b_+1] - T[i] <= k: b_ += 1
            return a_, b_
        XS, YS = [], []
        for i in range(n):
            a_, b_ = win(i, 3); XS.append(sum(X[a_:b_+1]) / (b_-a_+1)); YS.append(sum(Y[a_:b_+1]) / (b_-a_+1))
        vel = []
        for i in range(n):
            if con_vel and P[i][4] is not None:
                vel.append(P[i][4]); continue
            a_, b_ = win(i, 2); dt = T[b_] - T[a_]
            vel.append(math.hypot(XS[b_] - XS[a_], YS[b_] - YS[a_]) / dt if dt > 0 else 0.0)
        t0 = P[0][0]
        loc0 = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc) + datetime.timedelta(hours=utc_offset_h)
        base = "WingFoil_" + loc0.strftime('%Y-%m-%d_%H-%M-%S')
        d = os.path.join(sessions_root, base); k = 2
        while os.path.exists(d):
            d = os.path.join(sessions_root, f"{base}_importado{'' if k == 2 else k}"); k += 1
        os.makedirs(d)
        with open(os.path.join(d, 'Location.csv'), 'w', encoding='utf-8') as f:
            f.write('time,seconds_elapsed,bearingAccuracy,speedAccuracy,verticalAccuracy,horizontalAccuracy,speed,bearing,altitude,longitude,latitude\n')
            for p, v in zip(P, vel):
                acc = '' if p[5] is None else f"{p[5] * 5:.2f}"          # hdop -> metros aproximados
                ele = '' if p[3] is None else f"{p[3]:.2f}"
                f.write(f"{int(round(p[0] * 1e9))},{p[0] - t0:.3f},,,,{acc},{v:.4f},,{ele},{p[2]:.8f},{p[1]:.8f}\n")
        dts = sorted(P[i+1][0] - P[i][0] for i in range(n-1))
        paso = dts[len(dts)//2] if dts else 1
        app = 'GPX importado' + (f" - {creator}".replace(',', ' ') if creator else '')
        with open(os.path.join(d, 'Metadata.csv'), 'w', encoding='utf-8') as f:
            f.write('version,device name,recording epoch time,recording time,recording timezone,platform,appVersion,device id,sensors,sampleRateMs,standardisation\n')
            f.write(','.join(['3', (creator or 'GPX').replace(',', ' '), str(int(round(t0 * 1000))), loc0.strftime('%Y-%m-%d_%H-%M-%S'),
                              'local', 'gpx', app, os.path.basename(d), 'Location' if con_vel else 'Location|velocidad-por-posicion',
                              str(int(round(paso * 1000))), 'false']) + '\n')
        try: shutil.copyfile(gpx_path, os.path.join(d, 'original.gpx'))
        except Exception: pass
        info = {'importado': '1', 'archivo_importado': archivo or os.path.basename(gpx_path), 'velocidad_gpx': '1' if con_vel else '0'}
        if nombre: info['nombre'] = nombre[:80]
        with open(os.path.join(d, 'info.json'), 'w', encoding='utf-8') as f: json.dump(info, f, ensure_ascii=False)
        dur = P[-1][0] - t0
        return json.dumps({'ok': True, 'dir': d, 'puntos': n, 'inicio': loc0.strftime('%d/%m/%Y %H:%M'),
                           'duracion_min': round(dur / 60, 1), 'paso_s': round(paso, 1), 'velocidad_gpx': con_vel, 'nombre': nombre}, ensure_ascii=False)
    except ET.ParseError as e:
        return json.dumps({'ok': False, 'error': f"El archivo no es un GPX válido ({e})."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'ok': False, 'error': f"{type(e).__name__}: {e}"}, ensure_ascii=False)
