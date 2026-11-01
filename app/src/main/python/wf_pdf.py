"""PDF del Análisis WingFoil — escritor de PDF en Python puro (sin dependencias).
Uso: python3 wf_pdf.py resultados.json salida.pdf   (el JSON lo genera wingfoil_analisis.py --json)"""
import json, math, sys, zlib, os, hashlib
_W_REG = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 761, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 761, 611, 761, 761, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 761, 500, 667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500]
_W_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 761, 556, 761, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 761, 611, 761, 761, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 761, 500, 667, 278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556]

W, H = 595.28, 841.89          # A4 en puntos
M = 36                         # margen

def _hex(c):
    c = c.lstrip('#'); return tuple(int(c[i:i+2], 16)/255 for i in (0, 2, 4))

def text_width(s, size, bold=False):
    tb = _W_BOLD if bold else _W_REG
    tot = 0
    for ch in s.encode('cp1252', 'replace'):
        tot += tb[ch-32] if 32 <= ch < 256 else 556
    return tot * size / 1000

def _esc(s):
    b = s.encode('cp1252', 'replace')
    return b.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')

class PDF:
    def __init__(self): self.pages = []; self.c = None; self.images = []
    def add_jpeg(self, data):
        info = jpeg_info(data)
        if not info: return None
        self.images.append((data,) + info); return f"Im{len(self.images)}"
    def image(self, name, x, y, w, h):
        self._o(f"q {w:.3f} 0 0 {h:.3f} {x:.3f} {H-y-h:.3f} cm /{name} Do Q\n")
    def clip_begin(self, x, y, w, h): self._o(f"q {x:.2f} {H-y-h:.2f} {w:.2f} {h:.2f} re W n\n")
    def clip_end(self): self._o("Q\n")
    def shade(self, x, y, w, h, color, alpha):
        self._o(f"q /GS{int(alpha*100)} gs {self._col(color, 'rg')} {x:.2f} {H-y-h:.2f} {w:.2f} {h:.2f} re f Q\n")
        self.alphas.add(int(alpha*100)) if hasattr(self, 'alphas') else setattr(self, 'alphas', {int(alpha*100)})
    def page(self):
        self.c = []; self.pages.append(self.c)
    def _o(self, s): self.c.append(s.encode('latin-1') if isinstance(s, str) else s)
    # coordenadas con origen ARRIBA a la izquierda
    def _col(self, c, op):
        r, g, b = _hex(c); return f"{r:.3f} {g:.3f} {b:.3f} {op}"
    def text(self, x, y, s, size=10, bold=False, color='#000000', align='left'):
        s = str(s)
        if align != 'left':
            w = text_width(s, size, bold); x -= w if align == 'right' else w/2
        self._o(f"BT /{'F2' if bold else 'F1'} {size:.2f} Tf {self._col(color, 'rg')} {x:.2f} {H-y:.2f} Td (")
        self._o(_esc(s)); self._o(") Tj ET\n")
    def fit(self, s, size, maxw, bold=False):
        s = str(s)
        if text_width(s, size, bold) <= maxw: return s
        while s and text_width(s + '…', size, bold) > maxw: s = s[:-1]
        return s + '…'
    def wrap(self, s, size, maxw, bold=False):
        out, cur = [], ''
        for w_ in str(s).split():
            t_ = (cur + ' ' + w_).strip()
            if text_width(t_, size, bold) <= maxw: cur = t_
            else:
                if cur: out.append(cur)
                cur = w_
        if cur: out.append(cur)
        return out
    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.5):
        ops = []
        if fill: ops.append(self._col(fill, 'rg'))
        if stroke: ops.append(self._col(stroke, 'RG') + f" {lw:.2f} w")
        op = 'B' if fill and stroke else 'f' if fill else 'S'
        self._o(" ".join(ops) + f" {x:.2f} {H-y-h:.2f} {w:.2f} {h:.2f} re {op}\n")
    def polyline(self, pts, color, lw=1.0):
        if len(pts) < 2: return
        s = [self._col(color, 'RG'), f"{lw:.2f} w 1 J 1 j", f"{pts[0][0]:.2f} {H-pts[0][1]:.2f} m"]
        s += [f"{x:.2f} {H-y:.2f} l" for x, y in pts[1:]]
        self._o(" ".join(s) + " S\n")
    def polygon(self, pts, fill=None, stroke=None, lw=0.6):
        s = []
        if fill: s.append(self._col(fill, 'rg'))
        if stroke: s.append(self._col(stroke, 'RG') + f" {lw:.2f} w")
        s.append(f"{pts[0][0]:.2f} {H-pts[0][1]:.2f} m")
        s += [f"{x:.2f} {H-y:.2f} l" for x, y in pts[1:]]
        s.append('h ' + ('B' if fill and stroke else 'f' if fill else 'S'))
        self._o(" ".join(s) + "\n")
    def circle(self, cx, cy, r, fill=None, stroke=None, lw=0.6):
        k = 0.5523 * r; y = H - cy
        s = []
        if fill: s.append(self._col(fill, 'rg'))
        if stroke: s.append(self._col(stroke, 'RG') + f" {lw:.2f} w")
        s.append(f"{cx+r:.2f} {y:.2f} m {cx+r:.2f} {y+k:.2f} {cx+k:.2f} {y+r:.2f} {cx:.2f} {y+r:.2f} c "
                 f"{cx-k:.2f} {y+r:.2f} {cx-r:.2f} {y+k:.2f} {cx-r:.2f} {y:.2f} c "
                 f"{cx-r:.2f} {y-k:.2f} {cx-k:.2f} {y-r:.2f} {cx:.2f} {y-r:.2f} c "
                 f"{cx+k:.2f} {y-r:.2f} {cx+r:.2f} {y-k:.2f} {cx+r:.2f} {y:.2f} c h " + ('B' if fill and stroke else 'f' if fill else 'S'))
        self._o(" ".join(s) + "\n")
    def save(self, path):
        objs = []
        def add(b): objs.append(b); return len(objs)
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        img_ids = []
        for data, w_, h_, cs in self.images:
            img_ids.append(add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (w_, h_, cs.encode(), len(data)) + data + b"\nendstream"))
        xo = " ".join(f"/Im{i} {o} 0 R" for i, o in enumerate(img_ids, 1))
        gs = " ".join(f"/GS{a} << /Type /ExtGState /ca {a/100:.2f} /CA {a/100:.2f} >>" for a in sorted(getattr(self, 'alphas', set())))
        extra = (f" /XObject << {xo} >>" if xo else "") + (f" /ExtGState << {gs} >>" if gs else "")
        pages_id = len(objs) + 1 + 2*len(self.pages)
        kids = []
        for c in self.pages:
            data = zlib.compress(b"".join(c))
            cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
            kids.append(add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                             "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >>%s >> >>" % (pages_id, W, H, cid, f1, f2, extra)).encode()))
        assert add(("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{k} 0 R" for k in kids), len(kids))).encode()) == pages_id
        cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
        info = add(b"<< /Producer (Wingfoil Tracker) /Title (Analisis Wingfoil) >>")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offs = []
        for i, b in enumerate(objs, 1):
            offs.append(len(out)); out += b"%d 0 obj\n" % i + b + b"\nendobj\n"
        x = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs)+1)
        for o in offs: out += b"%010d 00000 n \n" % o
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs)+1, cat, info, x)
        open(path, 'wb').write(bytes(out))

def jpeg_info(d):
    """(ancho, alto, espacio de color) de un JPEG, o None si no es un JPEG utilizable."""
    if len(d) < 4 or d[:2] != b'\xff\xd8': return None
    i = 2
    while i + 9 < len(d):
        if d[i] != 0xFF: i += 1; continue
        mk = d[i+1]
        if mk in (0xD8, 0x01) or 0xD0 <= mk <= 0xD7: i += 2; continue
        L = int.from_bytes(d[i+2:i+4], 'big')
        if mk in (0xC0, 0xC1, 0xC2):
            h_ = int.from_bytes(d[i+5:i+7], 'big'); w_ = int.from_bytes(d[i+7:i+9], 'big'); nc = d[i+9]
            cs = {1: 'DeviceGray', 3: 'DeviceRGB'}.get(nc)
            return (w_, h_, cs) if cs else None
        i += 2 + L
    return None

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ATRIB = "Imagen satelital: Esri, Maxar, Earthstar Geographics y la comunidad de usuarios GIS"

def _fetch_default(url):
    """En la app usa la descarga de Android (con caché); en la computadora, urllib."""
    try:
        from java import jclass
        b = jclass('uy.wingfoil.tracker.Tiles').get(url)
        return bytes(b) if b is not None else None
    except ImportError:
        pass
    try:
        import urllib.request
        rq = urllib.request.Request(url, headers={'User-Agent': 'WingfoilTracker/1.1'})
        return urllib.request.urlopen(rq, timeout=10).read()
    except Exception:
        return None

def _merc(lat, lon, z):
    n = 256 * 2**z
    la = max(-85.0, min(85.0, lat))
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(la)) + 1/math.cos(math.radians(la))) / math.pi) / 2 * n
    return x, y

# ---------------------------------------------------------------- informe
NAVY = '#0B2545'; ACC = '#13A3D8'; GRIS = '#5B6B7F'; CLARO = '#EEF3F8'
SPD = [('#FFFFFF', 'menos de 4 kn'), ('#00D84A', '4 a 7 kn'), ('#FFD400', '7 a 12 kn'), ('#FF2D2D', 'más de 12 kn')]
FILL = {('Virada', 'Completa'): '#C6EFCE', ('Virada', 'Fallida'): '#FFC7CE',
        ('Trasluchada', 'Completa'): '#DDEBF7', ('Trasluchada', 'Fallida'): '#FCE4D6'}
MK = {('Trasluchada', 'Completa'): '#22C55E', ('Trasluchada', 'Fallida'): '#FF8A00',
      ('Virada', 'Completa'): '#22C55E', ('Virada', 'Fallida'): '#EF4444'}

def _n(x, d=1, suf=''):
    return 's/d' if x is None else (f"{x:.{d}f}".replace('.', ',') + suf)
def _pct(x, signo=False):
    if x is None: return 's/d'
    s = f"{x*100:+.1f}" if signo else f"{x*100:.1f}"
    return s.replace('.', ',') + '%'
def _bk(v): return 0 if v < 4 else 1 if v < 7 else 2 if v < 12 else 3

def _marker(p, x, y, tipo, res, r=3.6):
    col = MK[(tipo, res)]
    if tipo == 'Trasluchada': p.circle(x, y, r, fill=col, stroke='#FFFFFF', lw=0.6)
    else: p.polygon([(x, y-r*1.25), (x+r*1.15, y), (x, y+r*1.25), (x-r*1.15, y)], fill=col, stroke='#FFFFFF', lw=0.6)

def _star(p, x, y, r, col):
    pts = []
    for i in range(10):
        a = -math.pi/2 + i*math.pi/5; rr = r if i % 2 == 0 else r*0.45
        pts.append((x + rr*math.cos(a), y + rr*math.sin(a)))
    p.polygon(pts, fill=col, stroke='#FFFFFF', lw=0.6)

def _arrow(p, cx, cy, deg_to, L, col, lw=1.6):
    """Flecha centrada en (cx,cy) apuntando hacia el rumbo deg_to (0 = norte)."""
    a = math.radians(deg_to); dx, dy = math.sin(a), -math.cos(a)
    x0, y0 = cx - dx*L/2, cy - dy*L/2; x1, y1 = cx + dx*L/2, cy + dy*L/2
    p.polyline([(x0, y0), (x1, y1)], col, lw)
    h = L*0.32; b = math.radians(25)
    for s_ in (1, -1):
        ang = math.atan2(-dy, -dx) + s_*b
        p.polyline([(x1, y1), (x1 + h*math.cos(ang), y1 + h*math.sin(ang))], col, lw)

def mapa(p, R, x, y, w, h, sat=True, fetch=None):
    tr = R['track']
    p.rect(x, y, w, h, fill='#0E2A47')
    if len(tr) < 2: return False
    lats = [q[0] for q in tr] + [m['lat'] for m in R['maniobras']]
    lons = [q[1] for q in tr] + [m['lon'] for m in R['maniobras']]
    pad = 22
    # zoom: el más alto con el que el recorrido entra en ~2 píxeles por punto del mapa
    z = 18
    while z > 3:
        x0, y0 = _merc(max(lats), min(lons), z); x1, y1 = _merc(min(lats), max(lons), z)
        if (x1 - x0) <= (w - 2*pad) * 2.2 and (y1 - y0) <= (h - 2*pad) * 2.2: break
        z -= 1
    x0, y0 = _merc(max(lats), min(lons), z); x1, y1 = _merc(min(lats), max(lons), z)
    s = min((w - 2*pad) / max(x1 - x0, 1e-9), (h - 2*pad) / max(y1 - y0, 1e-9))     # puntos por píxel
    ox = x + pad + ((w - 2*pad) - (x1 - x0)*s)/2 - x0*s
    oy = y + pad + ((h - 2*pad) - (y1 - y0)*s)/2 - y0*s
    def P(la, lo):
        mx, my = _merc(la, lo, z); return (ox + mx*s, oy + my*s)
    # fondo satelital
    con_sat = False
    if sat:
        fetch = fetch or _fetch_default
        tx0 = int(((x - ox)/s) // 256); tx1 = int(((x + w - ox)/s) // 256)
        ty0 = int(((y - oy)/s) // 256); ty1 = int(((y + h - oy)/s) // 256)
        nmax = 2**z
        tiles = [(tx, ty) for ty in range(max(0, ty0), min(nmax-1, ty1)+1) for tx in range(tx0, tx1+1)]
        if len(tiles) <= 90:
            p.clip_begin(x, y, w, h)
            ok = 0
            for tx, ty in tiles:
                d = fetch(TILE_URL.format(z=z, x=tx % nmax, y=ty))
                nm = p.add_jpeg(d) if d else None
                if not nm: continue
                p.image(nm, ox + tx*256*s, oy + ty*256*s, 256*s + 0.4, 256*s + 0.4); ok += 1
            if ok:
                con_sat = True
                p.shade(x, y, w, h, '#000000', 0.28)     # oscurece un poco para que resalte el track
            p.clip_end()
    # track por color (sin unir segmentos distintos), con borde oscuro para que se lea sobre la foto
    tramos = []; cur, cb = [], None
    for a, b in zip(tr, tr[1:]):
        if a[3] != b[3]:
            if len(cur) > 1: tramos.append((cb, cur))
            cur, cb = [], None; continue
        bu = _bk((a[2]+b[2])/2)
        if bu != cb:
            if len(cur) > 1: tramos.append((cb, cur))
            cur, cb = [P(a[0], a[1])], bu
        cur.append(P(b[0], b[1]))
    if len(cur) > 1: tramos.append((cb, cur))
    if con_sat:
        for cb_, pts in tramos: p.polyline(pts, '#111111', 2.2)
    for cb_, pts in tramos: p.polyline(pts, SPD[cb_][0], 1.1)
    for a, b in zip(tr, tr[1:]):
        if a[3] != b[3]:
            for q in (a, b):
                px, py = P(q[0], q[1]); p.circle(px, py, 1.6, fill='#9AA9BC')
    # maniobras
    lbl = len(R['maniobras']) <= 45
    for m in R['maniobras']:
        px, py = P(m['lat'], m['lon']); _marker(p, px, py, m['tipo'], m['resultado'])
        if lbl:
            num = m['nombre'].split('#')[1].split(' ')[0]
            p.text(px+4.5, py-3, ('T' if m['tipo'] == 'Trasluchada' else 'V') + num + ('f' if m['resultado'] == 'Fallida' else ''), 5.5, True, '#FFFFFF')
    px, py = P(R['vmax20_lat'], R['vmax20_lon']); _star(p, px, py, 6.5, '#B44CFF')
    # norte, viento y escala (con fondo para que se lean sobre la foto)
    p.rect(x + w - 50, y + 8, 44, 112, fill='#0E2A47')
    nx, ny = x + w - 28, y + 34
    _arrow(p, nx, ny, 0, 22, '#FFFFFF', 1.4); p.text(nx, ny - 15, 'N', 8, True, '#FFFFFF', 'center')
    wx, wy = x + w - 28, y + 84
    _arrow(p, wx, wy, (R['viento'] + 180) % 360, 26, '#7FDBFF', 2.0)
    p.text(wx, wy + 25, f"{R['viento']:.0f}°", 7.5, True, '#7FDBFF', 'center')
    p.text(wx, wy - 20, "Viento", 6.5, True, '#7FDBFF', 'center')
    lat_c = sum(lats)/len(lats)
    mpp = 156543.03392 * math.cos(math.radians(lat_c)) / 2**z / s     # metros por punto
    for nice in (50, 100, 200, 250, 500, 1000, 2000, 5000):
        if nice/mpp > w*0.18: break
    L = nice/mpp; bx, by = x + 14, y + h - 16
    p.rect(bx - 6, by - 14, L + 12, 22, fill='#0E2A47')
    p.rect(bx, by, L, 3, fill='#FFFFFF')
    p.text(bx, by - 4, f"{nice} m" if nice < 1000 else f"{nice//1000} km", 7, True, '#FFFFFF')
    if con_sat:
        p.text(x + w - 4, y + h - 4, ATRIB, 5, False, '#FFFFFF', 'right')
    return con_sat

def informe(R, path, sat=True, fetch=None):
    p = PDF(); p.page()
    # encabezado
    p.rect(0, 0, W, 78, fill=NAVY)
    p.text(M, 34, f"Análisis Wingfoil — {R['fecha']}", 21, True, '#FFFFFF')
    p.text(M, 54, f"Viento desde {R['viento']:.0f}°   ·   {R['hora_inicio']} a {R['hora_fin']}   ·   {R['origen']}", 9.5, False, '#BFD7EA')
    if R['excluidos']:
        p.text(M, 68, "Tramos excluidos: " + ", ".join(f"{a}–{b}" for a, b in R['excluidos']), 8, False, '#BFD7EA')
    # tarjetas
    T, V = R['por_tipo']['Trasluchada'], R['por_tipo']['Virada']
    tiles = [("Distancia", _n(R['distancia_km'], 2, ' km'), ''),
             ("Tiempo", _n(R['tiempo_min'], 1, ' min'), ''),
             ("Planeo (>7 kn)", _pct(R['planeo_pct']), _n(R['planeo_min'], 1, ' min')),
             ("Vel. media en planeo", _n(R['vel_media_planeo'], 2, ' kn'), ''),
             ("Vel. máx. en 20 m", _n(R['vmax20'], 2, ' kn'), R['vmax20_hora']),
             ("Trasluchadas", f"{T['completas']} / {T['fallidas']}", f"completas / fallidas · éxito {_pct(T['exito'])}"),
             ("Viradas", f"{V['completas']} / {V['fallidas']}", f"completas / fallidas · éxito {_pct(V['exito'])}"),
             ("Cortes de señal", str(R['cortes']), f"{_n(R['sin_senal_min'], 1, ' min')} sin señal")]
    tw = (W - 2*M - 3*8) / 4; th = 52
    for i, (l, v_, sub) in enumerate(tiles):
        cx = M + (i % 4)*(tw + 8); cy = 92 + (i // 4)*(th + 8)
        p.rect(cx, cy, tw, th, fill=CLARO)
        p.rect(cx, cy, 3, th, fill=ACC)
        p.text(cx + 10, cy + 14, l.upper(), 7, True, GRIS)
        p.text(cx + 10, cy + 33, v_, 16, True, NAVY)
        if sub: p.text(cx + 10, cy + 45, p.fit(sub, 6.8, tw - 14), 6.8, False, GRIS)
    # mapa
    my = 92 + 2*(th + 8) + 4; mh = H - my - 80
    con_sat = mapa(p, R, M, my, W - 2*M, mh, sat, fetch)
    # leyenda
    ly = my + mh + 16; lx = M
    p.text(lx, ly, "Velocidad:", 7.5, True, NAVY); lx += 44
    for col, l in SPD:
        p.rect(lx, ly - 6, 14, 5, fill=col, stroke='#8899AA', lw=0.4); p.text(lx + 18, ly, l, 7.5, False, GRIS)
        lx += 22 + text_width(l, 7.5) + 10
    ly += 14; lx = M
    p.text(lx, ly, "Maniobras:", 7.5, True, NAVY); lx += 44
    for (ty, rs), lab in ((('Trasluchada', 'Completa'), 'Trasluchada completa'), (('Trasluchada', 'Fallida'), 'Trasluchada fallida'),
                          (('Virada', 'Completa'), 'Virada completa'), (('Virada', 'Fallida'), 'Virada fallida')):
        _marker(p, lx + 4, ly - 3, ty, rs, 3.4); p.text(lx + 11, ly, lab, 7.5, False, GRIS); lx += 18 + text_width(lab, 7.5) + 8
    _star(p, lx + 5, ly - 3, 5, '#B44CFF'); p.text(lx + 13, ly, "Vel. máx. 20 m", 7.5, False, GRIS)
    nota = "Etiquetas del mapa: T = trasluchada, V = virada, número de su grupo, f = fallida (como en el KML y la tabla)." if len(R['maniobras']) <= 45 else "Los nombres de cada maniobra están en la tabla y en el KML."
    if sat and not con_sat: nota += "  Sin imagen satelital (no había conexión a internet)."
    p.text(M, ly + 14, nota, 6.8, False, GRIS)

    # ---------- página 2: resumen detallado y maniobras
    p.page(); y = 50
    p.text(M, y, "Resumen de la sesión", 15, True, NAVY); y += 14
    filas = [("Origen del archivo", R['origen']), ("Dirección del viento (desde)", f"{R['viento']:.0f}°"),
             ("Distancia total recorrida", _n(R['distancia_km'], 2, ' km')), ("Tiempo total del recorrido", _n(R['tiempo_min'], 1, ' min')),
             ("Tiempo total de planeo (>7 nudos)", _n(R['planeo_min'], 1, ' min')), ("% del tiempo planeando", _pct(R['planeo_pct'])),
             ("Velocidad media de navegación en planeo (>7 nudos)", _n(R['vel_media_planeo'], 2, ' kn')),
             ("Velocidad máxima en un tramo de 20 m", f"{_n(R['vmax20'], 2, ' kn')}  ({R['vmax20_hora']})"),
             ("Viradas completas / fallidas", f"{V['completas']} / {V['fallidas']}"), ("% de éxito en viradas", _pct(V['exito'])),
             ("Trasluchadas completas / fallidas", f"{T['completas']} / {T['fallidas']}"), ("% de éxito en trasluchadas", _pct(T['exito'])),
             ("Trasluchadas: velocidad promedio de entrada", _n(T['v_in'], 2, ' kn')), ("Trasluchadas: velocidad promedio de salida", _n(T['v_out'], 2, ' kn')),
             ("Trasluchadas: variación promedio salida vs entrada", _pct(T['variacion'], True)),
             ("Viradas: velocidad promedio de entrada", _n(V['v_in'], 2, ' kn')), ("Viradas: velocidad promedio de salida", _n(V['v_out'], 2, ' kn')),
             ("Viradas: variación promedio salida vs entrada", _pct(V['variacion'], True)),
             ("Cortes de señal GPS", str(R['cortes'])), ("Tiempo total sin señal", _n(R['sin_senal_min'], 1, ' min')),
             (f"Puntos descartados por precisión (> {R['max_acc']:g} m)", str(R['descartados_precision']))]
    for i, (l, v_) in enumerate(filas):
        if i % 2 == 0: p.rect(M, y, W - 2*M, 15, fill=CLARO)
        neg = v_.startswith('-') and v_.endswith('%')
        p.text(M + 6, y + 10.5, l, 8.5, False, '#222222')
        p.text(W - M - 6, y + 10.5, p.fit(v_, 8.5, 230, True), 8.5, True, '#C00000' if neg else NAVY, 'right')
        y += 15
    y += 22
    cols = [("Nombre", 128, 'left'), ("Hora", 50, 'center'), ("Transc.", 42, 'center'), ("Entrada", 50, 'right'),
            ("Salida", 50, 'right'), ("Variación", 54, 'right'), ("Observación", 0, 'left')]
    used = sum(c[1] for c in cols); cols[-1] = (cols[-1][0], W - 2*M - used, 'left')
    def head(y):
        p.text(M, y, "Maniobras", 15, True, NAVY); y += 10
        p.rect(M, y, W - 2*M, 18, fill=NAVY); xx = M
        for nm, cw, al in cols:
            tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
            p.text(tx, y + 12, nm + (" (kn)" if nm in ("Entrada", "Salida") else ""), 7.5, True, '#FFFFFF', al); xx += cw
        return y + 18
    MS = R['maniobras']
    if not MS:
        p.text(M, y, "Maniobras", 15, True, NAVY); p.text(M, y + 20, "No se detectaron viradas ni trasluchadas en esta sesión.", 9, False, GRIS)
    else:
        if y > H - 120: p.page(); y = 50
        y = head(y)
        for m in MS:
            if y > H - 50:
                p.page(); y = head(50)
            p.rect(M, y, W - 2*M, 14, fill=FILL[(m['tipo'], m['resultado'])])
            vals = [m['nombre'], m['hora'], m['transcurrido'], _n(m['v_in'], 1), _n(m['v_out'], 1), _pct(m['variacion'], True), m['nota']]
            xx = M
            for (nm, cw, al), val in zip(cols, vals):
                tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
                col = '#C00000' if nm == 'Variación' and val.startswith('-') else '#222222'
                p.text(tx, y + 10, p.fit(val, 7.8, cw - 8), 7.8, nm == 'Nombre', col, al); xx += cw
            y += 14
        y += 16
        if y < H - 60:
            for ln in p.wrap('"Completa" = sin caída sostenida (2+ muestras seguidas) bajo 4 nudos en los 40 m posteriores al giro; "Fallida" = con esa caída, o si la señal GPS se corta antes de completar los 40 m. Se excluyen las maniobras con entrada (40 m previos) menor a 6 nudos y los giros complejos. Entrada/Salida = velocidad media 40 m antes/después.', 7, W - 2*M):
                p.text(M, y, ln, 7, False, GRIS); y += 9.5
    for i, c in enumerate(p.pages, 1):           # pie de página
        p.c = c; p.text(W/2, H - 18, f"Wingfoil Tracker · Análisis WingFoil Completo · {R['fecha']} · página {i} de {len(p.pages)}", 7, False, '#8899AA', 'center')
    p.save(path)

if __name__ == '__main__':
    informe(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2])
    print("PDF:", sys.argv[2])
