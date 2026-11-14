"""PDF del Análisis WingFoil — escritor de PDF en Python puro (sin dependencias).
Uso: python3 wf_pdf.py resultados.json salida.pdf   (el JSON lo genera wingfoil_analisis.py --json)"""
import json, math, sys, zlib, os, hashlib
import wf_textos
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
        info = add(b"<< /Producer (Wingfoil Tracker) /Title (Analisis de sesion) >>")
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

SALTO_COL = {'Completo': '#00E5FF', 'Fallido': '#FF4FB0'}
def _salto_mk(p, x, y, r=4.2, res='Completo'):
    p.polygon([(x, y - r*1.3), (x + r*1.15, y + r*0.75), (x - r*1.15, y + r*0.75)], fill=SALTO_COL[res], stroke='#0B2545', lw=0.7)

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

def _zoom_for(lats, lons, w, h, pad, maxtiles=90):
    z = 18
    while z > 3:
        x0, y0 = _merc(max(lats), min(lons), z); x1, y1 = _merc(min(lats), max(lons), z)
        fits = (x1 - x0) <= (w - 2*pad) * 2.2 and (y1 - y0) <= (h - 2*pad) * 2.2
        if fits:
            s_ = min((w - 2*pad) / max(x1 - x0, 1e-9), (h - 2*pad) / max(y1 - y0, 1e-9))
            ntiles = (w/s_/256 + 2) * (h/s_/256 + 2)
            if ntiles <= maxtiles: break
        z -= 1
    return z

def _label_place(cx, cy, tw, th, taken, r=4.5):
    """Elige dónde poner la etiqueta para no pisar otras (derecha, izquierda, arriba, abajo, diagonales)."""
    cands = [(cx + r + 1.5, cy - th/2), (cx - r - 1.5 - tw, cy - th/2), (cx - tw/2, cy - r - 1.5 - th),
             (cx - tw/2, cy + r + 1.5), (cx + r, cy - r - th), (cx + r, cy + r), (cx - r - tw, cy - r - th), (cx - r - tw, cy + r)]
    def free(bx, by):
        return all(bx + tw < ax or ax + aw < bx or by + th < ay or ay + ah < by for ax, ay, aw, ah in taken)
    for bx, by in cands:
        if free(bx, by): return bx, by
    return cands[0]

def mapa(p, R, x, y, w, h, sat=True, fetch=None, rango=None, numeros=False):
    """Dibuja el mapa. rango=(d0, d1) en metros recorridos: se encuadra solo esa parte del track
    (el resto queda tenue de fondo). numeros=True: etiqueta cada maniobra con su N°."""
    tr = R['track']
    p.rect(x, y, w, h, fill='#0E2A47')
    if len(tr) < 2: return False
    def dentro(d): return rango is None or rango[0] <= d <= rango[1]
    foco = [q for q in tr if dentro(q[4])]
    mans = [m for m in R['maniobras'] if dentro(m['cd'])]
    if len(foco) < 2: foco = tr
    lats = [q[0] for q in foco] + [m['lat'] for m in mans]
    lons = [q[1] for q in foco] + [m['lon'] for m in mans]
    pad = 24
    z = _zoom_for(lats, lons, w, h, pad)
    x0, y0 = _merc(max(lats), min(lons), z); x1, y1 = _merc(min(lats), max(lons), z)
    s = min((w - 2*pad) / max(x1 - x0, 1e-9), (h - 2*pad) / max(y1 - y0, 1e-9))     # puntos por píxel
    ox = x + pad + ((w - 2*pad) - (x1 - x0)*s)/2 - x0*s
    oy = y + pad + ((h - 2*pad) - (y1 - y0)*s)/2 - y0*s
    def P(la, lo):
        mx, my = _merc(la, lo, z); return (ox + mx*s, oy + my*s)
    p.clip_begin(x, y, w, h)
    con_sat = False
    if sat:
        fetch = fetch or _fetch_default
        tx0 = int(((x - ox)/s) // 256); tx1 = int(((x + w - ox)/s) // 256)
        ty0 = int(((y - oy)/s) // 256); ty1 = int(((y + h - oy)/s) // 256)
        nmax = 2**z
        tiles = [(tx, ty) for ty in range(max(0, ty0), min(nmax-1, ty1)+1) for tx in range(tx0, tx1+1)]
        ok = 0
        for tx, ty in tiles:
            d = fetch(TILE_URL.format(z=z, x=tx % nmax, y=ty))
            nm = p.add_jpeg(d) if d else None
            if not nm: continue
            p.image(nm, ox + tx*256*s, oy + ty*256*s, 256*s + 0.4, 256*s + 0.4); ok += 1
        if ok:
            con_sat = True
            p.shade(x, y, w, h, '#000000', 0.28)     # oscurece un poco para que resalte el track
    # tramos de color (sin unir segmentos distintos)
    def tramos(pts, tenue):
        out = []; cur, cb = [], None
        for a, b in zip(pts, pts[1:]):
            if a[3] != b[3] or (not tenue and not (dentro(a[4]) and dentro(b[4]))) or (tenue and dentro(a[4]) and dentro(b[4])):
                if len(cur) > 1: out.append((cb, cur))
                cur, cb = [], None; continue
            bu = -1 if tenue else _bk((a[2]+b[2])/2)
            if bu != cb:
                if len(cur) > 1: out.append((cb, cur))
                cur, cb = [P(a[0], a[1])], bu
            cur.append(P(b[0], b[1]))
        if len(cur) > 1: out.append((cb, cur))
        return out
    vivos = tramos(tr, False)
    if con_sat:
        for _, pts in vivos: p.polyline(pts, '#111111', 2.4 if rango else 2.2)
    for cb_, pts in vivos: p.polyline(pts, SPD[cb_][0], 1.4 if rango else 1.1)
    for a, b in zip(tr, tr[1:]):
        if a[3] != b[3] and dentro(a[4]):
            for q in (a, b):
                px, py = P(q[0], q[1]); p.circle(px, py, 1.6, fill='#9AA9BC')
    # maniobras (y números)
    r_ = 4.6 if numeros else 3.6
    pos = []
    for m in mans:
        px, py = P(m['lat'], m['lon']); pos.append((m, px, py)); _marker(p, px, py, m['tipo'], m['resultado'], r_)
    sal = [e for e in R.get('saltos', []) if dentro(e['cd'])]
    spos = []
    for e in sal:
        px, py = P(e['lat'], e['lon']); spos.append((e, px, py)); _salto_mk(p, px, py, 5 if numeros else 4.2, e['resultado'])
    if dentro(R['vmax20_cd']):
        px, py = P(R['vmax20_lat'], R['vmax20_lon']); _star(p, px, py, 7 if numeros else 6.5, '#B44CFF')
    if numeros:
        taken = [(px - r_, py - r_, 2*r_, 2*r_) for _, px, py in pos] + [(px - 5, py - 6, 10, 11) for _, px, py in spos]
        for e, px, py in spos:
            t_ = 'S' + e['nombre'].split('#')[1].split(' ')[0] + f" {e['altura']:.1f} m".replace('.', ','); fs = 7.5; tw = text_width(t_, fs, True) + 4; th = 9
            bx, by = _label_place(px, py, tw, th, taken, 5)
            taken.append((bx, by, tw, th))
            p.rect(bx, by, tw, th, fill=SALTO_COL[e['resultado']], stroke='#0B2545', lw=0.6)
            p.text(bx + tw/2, by + 7, t_, fs, True, '#0B2545', 'center')
        for m, px, py in pos:
            t_ = str(m['n']); fs = 7.5; tw = text_width(t_, fs, True) + 4; th = 9
            bx, by = _label_place(px, py, tw, th, taken, r_)
            taken.append((bx, by, tw, th))
            p.rect(bx, by, tw, th, fill='#FFFFFF', stroke=MK[(m['tipo'], m['resultado'])], lw=0.8)
            p.text(bx + tw/2, by + 7, t_, fs, True, '#0B2545', 'center')
    # norte, viento y escala
    p.rect(x + w - 50, y + 8, 44, 112, fill='#0E2A47')
    nx, ny = x + w - 28, y + 34
    _arrow(p, nx, ny, 0, 22, '#FFFFFF', 1.4); p.text(nx, ny - 15, 'N', 8, True, '#FFFFFF', 'center')
    wx, wy = x + w - 28, y + 84
    _arrow(p, wx, wy, (R['viento'] + 180) % 360, 26, '#7FDBFF', 2.0)
    p.text(wx, wy + 25, f"{R['viento']:.0f}°", 7.5, True, '#7FDBFF', 'center')
    p.text(wx, wy - 20, "Viento", 6.5, True, '#7FDBFF', 'center')
    lat_c = sum(lats)/len(lats)
    mpp = 156543.03392 * math.cos(math.radians(lat_c)) / 2**z / s     # metros por punto
    for nice in (20, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if nice/mpp > w*0.15: break
    L = nice/mpp; bx, by = x + 14, y + h - 16
    p.rect(bx - 6, by - 14, L + 12, 22, fill='#0E2A47')
    p.rect(bx, by, L, 3, fill='#FFFFFF')
    p.text(bx, by - 4, f"{nice} m" if nice < 1000 else f"{nice//1000} km", 7, True, '#FFFFFF')
    if con_sat:
        p.text(x + w - 4, y + h - 4, ATRIB, 5, False, '#FFFFFF', 'right')
    p.clip_end()
    return con_sat

def _leyenda(p, y, completa=True, saltos=False):
    lx = M
    if completa:
        p.text(lx, y, "Velocidad:", 7.5, True, NAVY); lx += 44
        for col, l in SPD:
            p.rect(lx, y - 6, 14, 5, fill=col, stroke='#8899AA', lw=0.4); p.text(lx + 18, y, l, 7.5, False, GRIS)
            lx += 22 + text_width(l, 7.5) + 10
        if saltos:
            lx += 6
            for res_, lab_ in (('Completo', 'Salto completo'), ('Fallido', 'Salto fallido')):
                _salto_mk(p, lx + 4, y - 3, 3.8, res_); p.text(lx + 11, y, lab_, 7.5, False, GRIS); lx += 18 + text_width(lab_, 7.5) + 6
        y += 14; lx = M
    p.text(lx, y, "Maniobras:", 7.5, True, NAVY); lx += 44
    for (ty, rs), lab in ((('Trasluchada', 'Completa'), 'Trasluchada completa'), (('Trasluchada', 'Fallida'), 'Trasluchada fallida'),
                          (('Virada', 'Completa'), 'Virada completa'), (('Virada', 'Fallida'), 'Virada fallida')):
        _marker(p, lx + 4, y - 3, ty, rs, 3.4); p.text(lx + 11, y, lab, 7.5, False, GRIS); lx += 18 + text_width(lab, 7.5) + 8
    _star(p, lx + 5, y - 3, 5, '#B44CFF'); p.text(lx + 13, y, "Vel. máx. 20 m", 7.5, False, GRIS)
    return y

def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs: return None
    k = len(xs) // 2
    return xs[k] if len(xs) % 2 else (xs[k-1] + xs[k]) / 2

def navegacion(p, R):
    """Página de navegación entre maniobras: tiempo y velocidad por rumbo, ángulos de ceñida y de largo, VMG."""
    RB = R.get('rumbos'); ANG = R.get('angulos')
    if not RB or not R.get('nav_medida_min'): return
    WS = R.get('disciplina') == 'windsurf'
    p.page(); p.rect(0, 0, W, 58, fill=NAVY)
    p.text(M, 30, "Navegación por rumbo y VMG", 18, True, '#FFFFFF')
    p.text(M, 47, f"Viento desde {R['viento']:.0f}°  ·  tramos rectos a más de {R.get('v_nav', 7):g} kn ({_n(R['nav_medida_min'], 1, ' min')} medidos)", 8, False, '#BFD7EA')
    y = 82
    def par(t_, size=8.4, col='#222222'):
        nonlocal y
        for ln in p.wrap(t_, size, W - 2*M): p.text(M, y, ln, size, False, col); y += size + 3.4
        y += 3
    def tab(cab, filas, anchos):
        nonlocal y
        p.rect(M, y, sum(anchos), 16, fill=NAVY); xx = M
        for c_, w_ in zip(cab, anchos): p.text(xx + 5, y + 11, p.fit(c_, 7.6, w_ - 8, True), 7.6, True, '#FFFFFF'); xx += w_
        y += 16
        for i, f in enumerate(filas):
            p.rect(M, y, sum(anchos), 14, fill=CLARO if i % 2 else '#FFFFFF'); xx = M
            for j, (c_, w_) in enumerate(zip(f, anchos)): p.text(xx + 5, y + 10, p.fit(str(c_), 8, w_ - 8, j == 0), 8, j == 0, '#222222'); xx += w_
            y += 14
        y += 12
    p.text(M, y, "Tiempo y velocidad por rumbo", 11.5, True, NAVY); y += 14
    for k_, txt in wf_textos.rumbos(WS): par(f"{k_}: {txt}", 7.6, GRIS)
    filas = [[q['rumbo'], f"{q['desde']} a {q['hasta']}°", _n(q['min'], 1, ' min'), _pct(q['pct']), _n(q['v_media'], 1, ' kn'), _n(q['v_max'], 1, ' kn'),
              _n(q['v_babor'], 1, ' kn'), _n(q['v_estribor'], 1, ' kn')] for q in RB]
    tab(["Rumbo", "Al viento", "Tiempo", "% tiempo", "Vel. media", "Vel. máx.", "Babor", "Estribor"], filas, [70, 66, 62, 56, 64, 64, 70, 71])
    rapido = max((q for q in RB if q['v_media'] is not None and (q['min'] or 0) >= 1), key=lambda q: q['v_media'], default=None)
    if rapido: par(f"Tu rumbo más rápido fue el {rapido['rumbo'].lower()} ({_n(rapido['v_media'], 1, ' kn')} de media).")
    p.text(M, y + 4, "Ángulos al viento y VMG por amura", 11.5, True, NAVY); y += 18
    EX = wf_textos.resumen(WS)
    for k_ in ('Ángulo de ceñida', 'Ángulo en el largo', 'VMG medio contra el viento'):
        par(f"{k_}: {wf_textos.buscar(EX, k_)}", 7.6, GRIS)
    filas = []
    for ld in ('babor', 'estribor'):
        a_ = ANG.get(ld, {})
        filas.append([f"Viento por {ld}", _n(a_.get('cenida'), 0, '°'), _n(a_.get('vmg_up'), 2, ' kn'), _n(a_.get('min_up'), 1, ' min'),
                      _n(a_.get('largo'), 0, '°'), _n(a_.get('vmg_dn'), 2, ' kn'), _n(a_.get('min_dn'), 1, ' min')])
    tab(["Amura", "Ceñida", "VMG subiendo", "Tiempo", "Largo", "VMG bajando", "Tiempo"], filas, [92, 66, 80, 62, 66, 80, 77])
    txt = []
    cb, ce = (ANG.get('babor') or {}).get('cenida'), (ANG.get('estribor') or {}).get('cenida')
    if cb is not None and ce is not None:
        if abs(cb - ce) >= 4: txt.append(f"Ceñís más alto con viento por {'babor' if cb < ce else 'estribor'} ({min(cb, ce):.0f}° contra {max(cb, ce):.0f}°).")
        else: txt.append("Ceñís parecido con viento por los dos lados.")
    vb, ve = (ANG.get('babor') or {}).get('vmg_up'), (ANG.get('estribor') or {}).get('vmg_up')
    if vb is not None and ve is not None and abs(vb - ve) >= 0.3:
        txt.append(f"Subís mejor (más VMG) con viento por {'babor' if vb > ve else 'estribor'}.")
    if R.get('vmg_up') is not None:
        txt.append(f"Mejor VMG sostenido 10 s: {_n(R['vmg_up'], 1, ' kn')} subiendo" + (f" ({R['vmg_up_hora']})" if R.get('vmg_up_hora') else '') +
                   (f" y {_n(R['vmg_dn'], 1, ' kn')} bajando" + (f" ({R['vmg_dn_hora']})" if R.get('vmg_dn_hora') else '') if R.get('vmg_dn') is not None else '') + ".")
    if txt: par(" ".join(txt))
    par("Todos estos datos dependen de la dirección del viento ingresada: con unos grados de error, los ángulos y el VMG cambian. "
        "Conviene comparar sesiones con la dirección bien medida (por ejemplo, de una estación meteorológica cercana).", 7.4, GRIS)

def rendimiento(p, R):
    """Páginas de rendimiento de maniobras: velocidad de entrada, viento por babor/estribor, ángulos y evolución."""
    MS = R['maniobras']
    WS = R.get('disciplina') == 'windsurf'
    navegacion(p, R)
    if not MS: return
    dur = max([m.get('t_rel') or 0 for m in MS] + [R['tiempo_min'] * 60, 1])
    st = {'y': 0}
    def nueva():
        p.page(); p.rect(0, 0, W, 58, fill=NAVY)
        p.text(M, 30, "Rendimiento de maniobras", 18, True, '#FFFFFF')
        p.text(M, 47, f"Viento desde {R['viento']:.0f}°  ·  pérdida = variación de la velocidad media de 40 m después vs 40 m antes (mediana de las completas)", 8, False, '#BFD7EA')
        st['y'] = 82
    def lugar(h):
        if st['y'] + h > H - 40: nueva()
    def parrafo(t_, size=8.6, col='#222222', bold=False):
        lns = p.wrap(t_, size, W - 2*M, bold); lugar(len(lns) * (size + 3.4) + 4)
        for ln in lns: p.text(M, st['y'], ln, size, bold, col); st['y'] += size + 3.4
        st['y'] += 3
    def titulo(t_, size=11.5):
        lugar(110); st['y'] += 6; p.text(M, st['y'], t_, size, True, NAVY); st['y'] += 12
    def tabla(cab, filas, anchos, resaltar=()):
        lugar(16 + 14*len(filas) + 30)
        y = st['y']; p.rect(M, y, sum(anchos), 16, fill=NAVY); xx = M
        for c_, w_ in zip(cab, anchos):
            p.text(xx + 5, y + 11, p.fit(c_, 7.6, w_ - 8, True), 7.6, True, '#FFFFFF'); xx += w_
        y += 16
        for i, f in enumerate(filas):
            fill = '#FFF4CC' if i in resaltar else (CLARO if i % 2 else '#FFFFFF')
            p.rect(M, y, sum(anchos), 14, fill=fill); xx = M
            for j, (c_, w_) in enumerate(zip(f, anchos)):
                col = '#C00000' if isinstance(c_, str) and c_.startswith('-') and c_.endswith('%') else '#222222'
                p.text(xx + 5, y + 10, p.fit(str(c_), 8, w_ - 8, j == 0), 8, j == 0, col); xx += w_
            y += 14
        st['y'] = y + 17
    pct = lambda a, b: f"{round(100*a/b)}%" if b else 's/d'
    def perd(L):
        v_ = _med([m['variacion'] for m in L if m['resultado'] == 'Completa' and m['variacion'] is not None])
        return 's/d' if v_ is None else f"{v_*100:+.0f}%".replace('+-', '-')
    def exito(L): return pct(sum(m['resultado'] == 'Completa' for m in L), len(L))
    def ang(x_): return 's/d' if x_ is None else f"{x_:.0f}°"
    def kn(x_): return 's/d' if x_ is None else _n(x_, 1, ' kn')
    nueva()
    parrafo("Cómo leer los ángulos: el de entrada se mide entre el rumbo promedio de 10 a 3 s antes del giro y el eje que se cruza; el de salida, entre ese eje y el rumbo de 3 a 10 s después. "
            "El eje es la popa redonda en las trasluchadas y el enfachado (proa al viento) en las viradas: 0° = sobre el eje. "
            "«Viento por babor/estribor» es el lado del que venía el viento antes del giro. Los ángulos y el lado dependen de la dirección de viento ingresada.", 8, GRIS)
    for tipo, plural, eje in (('Trasluchada', 'Trasluchadas', 'popa'), ('Virada', 'Viradas', 'enfachado')):
        L = [m for m in MS if m['tipo'] == tipo]
        C = [m for m in L if m['resultado'] == 'Completa']; F = [m for m in L if m['resultado'] == 'Fallida']
        st['y'] += 6; lugar(150)
        p.rect(M, st['y'], W - 2*M, 22, fill=CLARO); p.rect(M, st['y'], 3, 22, fill=ACC)
        p.text(M + 10, st['y'] + 15, f"{plural}: {len(L)}  ({len(C)} completas, {len(F)} fallidas, {exito(L)} de éxito)", 12, True, NAVY)
        st['y'] += 30
        if len(L) < 3:
            parrafo(f"Con {len(L)} {plural.lower() if len(L) != 1 else tipo.lower()} no alcanza para analizar el rendimiento."); continue
        # 0) cómo fue el giro: completas vs fallidas
        if any(m.get('dur') is not None for m in L):
            titulo("Cómo fue el giro: completas vs fallidas")
            parrafo("Para qué sirve: compara cómo hacés el giro cuando sale bien y cuando te caés. La diferencia muestra qué cambiar "
                    "(por ejemplo, si en las fallidas el giro es más cerrado, más largo o llegás más lento).", 8, GRIS)
            def md(B, k, d, suf):
                return _n(_med([m.get(k) for m in B]), d, suf)
            def mds(B):
                x_ = _med([m.get('barlo') for m in B]); return 's/d' if x_ is None else f"{x_:+.0f} m".replace('+-', '-')
            filas = []
            for lab, k, d, suf in (("Vel. de entrada", 'v_in', 1, ' kn'), ("Vel. mínima en el giro", 'vmin', 1, ' kn'), ("Duración del giro", 'dur', 0, ' s'),
                                   ("Radio del giro", 'radio', 0, ' m'), ("Tiempo para recuperar el 80%", 't_rec', 0, ' s')):
                filas.append([lab, md(C, k, d, suf) if C else '-', md(F, k, d, suf) if F else '-'])
            filas.append(["Metros contra el viento", mds(C) if C else '-', mds(F) if F else '-'])
            if not WS:
                Pc = [m for m in L if m.get('planeo') is not None]
                filas.append(["Sin bajar de 7 kn (en planeo)", f"{sum(1 for m in C if m.get('planeo'))} de {len(C)}", f"{sum(1 for m in F if m.get('planeo'))} de {len(F)}"])
                filas.append(["Tocó el agua y siguió", f"{sum(1 for m in C if m.get('toque'))} de {len(C)}", '-'])
            tabla(["Mediana", "Completas", "Fallidas"], filas, [190, 125, 125])
            txt = []
            rc, rf = _med([m.get('radio') for m in C]), _med([m.get('radio') for m in F])
            if rc and rf and abs(rc - rf) / rc >= 0.2:
                txt.append(f"En las fallidas el giro es {'más cerrado' if rf < rc else 'más abierto'} ({rf:.0f} m contra {rc:.0f} m).")
            dc, df = _med([m.get('dur') for m in C]), _med([m.get('dur') for m in F])
            if dc and df and df - dc >= 2: txt.append(f"Las fallidas duran más ({df:.0f} s contra {dc:.0f} s): el giro se hace lento y se pierde la velocidad.")
            if not WS and C:
                pp = sum(1 for m in C if m.get('planeo')) / len(C)
                txt.append(f"El {round(pp*100)}% de las completas fue sin bajar de 7 kn (en planeo)." + (" El siguiente paso es lograrlo en más giros." if pp < 0.5 else ""))
            if WS and tipo == 'Virada':
                bc_ = _med([m.get('barlo') for m in C])
                if bc_ is not None: txt.append(f"En las viradas completas {'ganás' if bc_ >= 0 else 'perdés'} {abs(bc_):.0f} m contra el viento en el giro (mediana).")
            if txt: parrafo(" ".join(txt))
        # 1) velocidad de entrada
        titulo("Velocidad de entrada y éxito")
        parrafo("Para qué sirve: muestra si te caés más cuando llegás lento al giro, y a partir de qué velocidad las maniobras te salen bien.", 8, GRIS)
        cortes = ([(0, 8, 'menos de 8 kn'), (8, 12, '8 a 12 kn'), (12, 18, '12 a 18 kn'), (18, 99, '18 kn o más')] if WS else
                  [(0, 8, 'menos de 8 kn'), (8, 9.5, '8 a 9,5 kn'), (9.5, 11, '9,5 a 11 kn'), (11, 99, '11 kn o más')])
        filas = []
        for a_, b_, lab in cortes:
            B = [m for m in L if a_ <= m['v_in'] < b_]
            if B: filas.append([lab, str(len(B)), exito(B), perd(B)])
        tabla(["Velocidad de entrada", tipo + "s", "Éxito", "Pérdida (completas)"], filas, [150, 90, 80, 120])
        vc, vf = _med([m['v_in'] for m in C]), _med([m['v_in'] for m in F])
        txt = f"Las completas entraron a una mediana de {kn(vc)}" + (f" y las fallidas a {kn(vf)}." if F else ".")
        bajo = [m for m in L if m['v_in'] < 8]
        if len(bajo) >= 2 and sum(m['resultado'] == 'Completa' for m in bajo) / len(bajo) < 0.7:
            txt += f" Con menos de 8 kn el éxito baja a {exito(bajo)}: conviene llegar al giro con más velocidad."
        parrafo(txt)
        # 2) babor vs estribor
        titulo("Viento por babor vs viento por estribor")
        parrafo("Para qué sirve: casi todos tenemos un lado mejor. Separar las maniobras según de qué lado venía el viento antes del giro muestra cuál practicar.", 8, GRIS)
        filas = []; datos = {}
        for lado in ('babor', 'estribor'):
            B = [m for m in L if m.get('amura') == lado]; Bc = [m for m in B if m['resultado'] == 'Completa']
            datos[lado] = B
            filas.append([lado.capitalize(), str(len(B)), exito(B) if B else '-', kn(_med([m['v_in'] for m in B])) if B else '-',
                          ang(_med([m['ang_in'] for m in Bc])) if Bc else '-', ang(_med([m['ang_out'] for m in Bc])) if Bc else '-', perd(B) if Bc else '-'])
        tabla(["Viento por", tipo + "s", "Éxito", "Vel. entrada", f"Áng. entrada", f"Áng. salida", "Pérdida"],
              filas, [62, 62, 48, 68, 86, 86, 61])
        nb, ne = len(datos['babor']), len(datos['estribor'])
        if nb == 0 or ne == 0:
            falta = 'babor' if nb == 0 else 'estribor'
            parrafo(f"No hiciste {plural.lower()} con viento por {falta}: ese lado no se puede evaluar. Conviene practicar en las dos direcciones.")
        else:
            def ex_(B): return sum(m['resultado'] == 'Completa' for m in B) / len(B)
            def pv(B):
                v_ = _med([m['variacion'] for m in B if m['resultado'] == 'Completa' and m['variacion'] is not None]); return v_ if v_ is not None else 0
            eb, ee = ex_(datos['babor']), ex_(datos['estribor'])
            if abs(eb - ee) >= 0.08: debil = 'babor' if eb < ee else 'estribor'; motivo = "por el éxito"
            elif abs(pv(datos['babor']) - pv(datos['estribor'])) >= 0.03: debil = 'babor' if pv(datos['babor']) < pv(datos['estribor']) else 'estribor'; motivo = "por la velocidad que perdés"
            else: debil = None
            if debil:
                fuerte = 'estribor' if debil == 'babor' else 'babor'
                parrafo(f"Tu lado más débil es con viento por {debil} ({motivo}): {exito(datos[debil])} de éxito y {perd(datos[debil])} de velocidad, "
                        f"contra {exito(datos[fuerte])} y {perd(datos[fuerte])} con viento por {fuerte}. Es el lado para practicar.")
            else:
                parrafo("Los dos lados rinden parecido: no hay un lado claramente más débil.")
        # 3) ángulo de salida
        titulo(f"Ángulo de salida (desde la {'popa redonda' if eje == 'popa' else 'proa al viento'}) y velocidad")
        parrafo("Para qué sirve: salir muy cerca del eje deja la tabla lenta; abrir de más también cuesta. Muestra a qué ángulo de salida perdés menos velocidad.", 8, GRIS)
        filas = []; mejor = None; mv = None
        for a_, b_ in ((0, 45), (45, 90), (90, 135), (135, 181)):
            B = [m for m in C if m['ang_out'] is not None and a_ <= m['ang_out'] < b_]
            if not B: continue
            v_ = _med([m['variacion'] for m in B if m['variacion'] is not None])
            if len(B) >= 3 and v_ is not None and (mv is None or v_ > mv): mv = v_; mejor = len(filas)
            filas.append([f"{a_} a {min(b_, 180)}°" if a_ else f"menos de {b_}°", str(len(B)), perd(B), kn(_med([m['v_out'] for m in B]))])
        if filas:
            tabla(["Ángulo de salida", "Completas", "Pérdida", "Vel. salida"], filas, [150, 90, 80, 120], resaltar=(mejor,) if mejor is not None else ())
            if mejor is not None: parrafo(f"Perdés menos velocidad saliendo a {filas[mejor][0]} del eje ({filas[mejor][2]}).")
        # 4) ángulo de entrada
        titulo("Ángulo de entrada y éxito")
        parrafo("Para qué sirve: muestra desde qué rumbo arrancás el giro con más éxito (por ejemplo, si te conviene orzar o arribar más antes de empezar).", 8, GRIS)
        filas = []; mejor = None; me = None
        for a_, b_ in ((0, 45), (45, 90), (90, 135), (135, 181)):
            B = [m for m in L if m['ang_in'] is not None and a_ <= m['ang_in'] < b_]
            if not B: continue
            e_ = sum(m['resultado'] == 'Completa' for m in B) / len(B)
            if len(B) >= 3 and (me is None or e_ > me): me = e_; mejor = len(filas)
            filas.append([f"{a_} a {min(b_, 180)}°" if a_ else f"menos de {b_}°", str(len(B)), exito(B), perd(B)])
        if filas:
            tabla(["Ángulo de entrada", tipo + "s", "Éxito", "Pérdida (completas)"], filas, [150, 90, 80, 120], resaltar=(mejor,) if mejor is not None else ())
            if mejor is not None: parrafo(f"Tu mejor rango de entrada es {filas[mejor][0]} del eje: {filas[mejor][2]} de éxito.")
        # 5) evolución
        titulo("Evolución durante la sesión")
        parrafo("Para qué sirve: compara el principio, el medio y el final. Si el último tercio es peor, suele ser cansancio; si es mejor, entraste en calor.", 8, GRIS)
        filas = []
        for k, lab in enumerate(("Primer tercio", "Segundo tercio", "Último tercio")):
            B = [m for m in L if k*dur/3 <= (m.get('t_rel') or 0) < (k+1)*dur/3 + (1 if k == 2 else 0)]
            if B: filas.append([lab, str(len(B)), exito(B), perd(B)])
        tabla(["Parte de la sesión", tipo + "s", "Éxito", "Pérdida (completas)"], filas, [150, 90, 80, 120])

def informe(R, path, sat=True, fetch=None):
    for m in R['maniobras']:
        m['n'] = ('T' if m['tipo'] == 'Trasluchada' else 'V') + m['nombre'].split('#')[1].split(' ')[0]
    tr = R['track']
    if 'vmax20_cd' not in R:
        R['vmax20_cd'] = min(tr, key=lambda q: (q[0]-R['vmax20_lat'])**2 + (q[1]-R['vmax20_lon'])**2)[4] if tr else 0
    p = PDF(); p.page()
    # ---------- página 1: datos clave + track completo + código de colores
    p.rect(0, 0, W, 78, fill=NAVY)
    WS = R.get('disciplina') == 'windsurf'; DISC = 'Windsurf' if WS else 'Wingfoil'
    titulo = R.get('nombre') or f"Análisis {DISC} — {R['fecha']}"
    p.text(M, 34, p.fit(titulo, 21, W - 2*M, True), 21, True, '#FFFFFF')
    vkn = f" · {_n(R['viento_kn'], 0 if float(R['viento_kn']).is_integer() else 1)} kn" if R.get('viento_kn') is not None else ''
    partes = ([R['fecha']] if R.get('nombre') else []) + ([R['lugar']] if R.get('lugar') else []) + \
             [DISC] + [f"Viento desde {R['viento']:.0f}°{vkn}", f"{R['hora_inicio']} a {R['hora_fin']}", R['origen']]
    p.text(M, 54, p.fit("   ·   ".join(partes), 9.5, W - 2*M), 9.5, False, '#BFD7EA')
    if R['excluidos']:
        p.text(M, 68, "Tramos excluidos: " + ", ".join(f"{a}–{b}" for a, b in R['excluidos']), 8, False, '#BFD7EA')
    T, V = R['por_tipo']['Trasluchada'], R['por_tipo']['Virada']
    TL = R.get('tramo_largo')
    tiles = [*([("Tramo más largo sin caídas", f"{int(TL['dur_s'] // 60)}:{int(round(TL['dur_s'] % 60)):02d} min · {_n(TL['dist_km'], 2, ' km')}",
                 f"{TL['trasluchadas']} trasluchadas · {TL['viradas']} viradas", 2)] if TL else []),
             ("Distancia total", _n(R['distancia_km'], 2, ' km'), ''),
             ("Tiempo total", _n(R['tiempo_min'], 1, ' min'), ''),
             *([("Tiempo navegando (>4 kn)", _n(R.get('nav_min'), 1, ' min'), f"{_pct((R.get('nav_min') or 0) / R['tiempo_min'] if R['tiempo_min'] else None)} del tiempo"),
                ("Vel. media navegando", _n(R.get('vel_media_nav'), 2, ' kn'), '')] if WS else
               [("Planeo (>7 kn)", _n(R['planeo_min'], 1, ' min'), f"{_pct(R['planeo_pct'])} del tiempo"),
                ("Vel. media en planeo", _n(R['vel_media_planeo'], 2, ' kn'), '')]),
             ("Vel. máx. en 20 m", _n(R['vmax20'], 2, ' kn'), R['vmax20_hora']),
             ("Trasluchadas", f"{T['completas']} / {T['fallidas']}", f"compl./fall. · éxito {_pct(T['exito'])}"),
             ("Viradas", f"{V['completas']} / {V['fallidas']}", f"compl./fall. · éxito {_pct(V['exito'])}")]
    if R.get('acc'):
        SL = R.get('saltos', [])
        top_ = max(SL, key=lambda e: e['altura']) if SL else None
        sc_ = sum(e['resultado'] == 'Completo' for e in SL); sf_ = len(SL) - sc_
        tiles.insert(4, ("Saltos", f"{sc_} / {sf_}",
                         (f"compl./fall. · éxito {_pct(sc_ / len(SL))}" if SL else "ninguno en esta sesión")))
        tiles.append(("Salto más alto", _n(top_['altura'], 2, ' m') if top_ else 's/d',
                      f"{top_['hora']} · {top_['resultado'].lower()}" if top_ else "sin saltos"))
    # dos filas; cada fila reparte el ancho en partes iguales; todo centrado
    # cada recuadro ocupa 1 lugar (el del tramo más largo, 2); las dos filas se reparten los lugares
    tiles = [x if len(x) == 4 else (*x, 1) for x in tiles]
    tot_ = sum(x[3] for x in tiles); acc_ = 0; n1 = 0
    for x in tiles:
        if acc_ + x[3] > (tot_ + 1) // 2: break
        acc_ += x[3]; n1 += 1
    filas_t = [tiles[:n1], tiles[n1:]]
    th = 56
    for fi, fila in enumerate(filas_t):
        if not fila: continue
        lug = sum(x[3] for x in fila)
        u_ = (W - 2*M - (lug-1)*8) / lug
        xx_ = M
        for j, (l, v_, sub, pe) in enumerate(fila):
            tw = u_ * pe + 8 * (pe - 1)
            cx = xx_; xx_ += tw + 8; cy = 92 + fi*(th + 8); mx = cx + tw/2
            p.rect(cx, cy, tw, th, fill=CLARO); p.rect(cx, cy, tw, 3, fill=ACC)
            lab = l.upper(); fsl = 7
            while text_width(lab, fsl, True) > tw - 10 and fsl > 5.6: fsl -= 0.2
            p.text(mx, cy + 16, p.fit(lab, fsl, tw - 8, True), fsl, True, GRIS, 'center')
            fsv = 16 if lug <= 4 else 15
            p.text(mx, cy + 36, p.fit(v_, fsv, tw - 10, True), fsv, True, NAVY, 'center')
            if sub: p.text(mx, cy + 49, p.fit(sub, 6.8, tw - 8), 6.8, False, GRIS, 'center')
    my = 92 + 2*(th + 8) + 4; mh = H - my - 80
    con_sat = mapa(p, R, M, my, W - 2*M, mh, sat, fetch)
    ly = _leyenda(p, my + mh + 16, saltos=R.get('acc', False))
    nota = f"Track completo. En las páginas siguientes, el track en {R['secciones']} secciones con cada maniobra numerada (T = trasluchada, V = virada)."
    if sat and not con_sat: nota += "  Sin imagen satelital (no había conexión a internet)."
    p.text(M, ly + 14, nota, 6.8, False, GRIS)

    # ---------- una página por sección, con las maniobras numeradas
    NS = max(1, int(R['secciones'])); D = R['dist_total_m'] or (tr[-1][4] if tr else 0); sl = D / NS
    for k in range(NS):
        d0, d1 = k*sl, (k+1)*sl if k < NS-1 else D + 1
        pts = [q for q in tr if d0 <= q[4] <= d1]
        ms = [m for m in R['maniobras'] if d0 <= m['cd'] <= d1]
        p.page()
        p.rect(0, 0, W, 58, fill=NAVY)
        p.text(M, 28, f"Sección {k+1} de {NS}", 18, True, '#FFFFFF')
        h0 = h1 = ''
        if pts and 'epoch' in R:
            import datetime as _dt
            hf = lambda t_: (_dt.datetime.fromtimestamp(R['epoch'] + t_, _dt.timezone.utc) + _dt.timedelta(hours=R['utc'])).strftime('%H:%M:%S')
            h0, h1 = hf(pts[0][5]), hf(pts[-1][5])
        nT = [m for m in ms if m['tipo'] == 'Trasluchada']; nV = [m for m in ms if m['tipo'] == 'Virada']
        p.text(M, 46, f"{d0/1000:.1f} a {min(d1, D)/1000:.1f} km".replace('.', ',') + (f"   ·   {h0} a {h1}" if h0 else '') +
               f"   ·   Trasluchadas {sum(m['resultado']=='Completa' for m in nT)} completas / {sum(m['resultado']=='Fallida' for m in nT)} fallidas"
               f"   ·   Viradas {sum(m['resultado']=='Completa' for m in nV)} / {sum(m['resultado']=='Fallida' for m in nV)}" +
               (f"   ·   Saltos {sum(1 for e in R.get('saltos', []) if d0 <= e['cd'] <= d1 and e['resultado'] == 'Completo')} / {sum(1 for e in R.get('saltos', []) if d0 <= e['cd'] <= d1 and e['resultado'] == 'Fallido')}" if R.get('acc') else ''), 8.5, False, '#BFD7EA')
        top = 70; mh2 = H - top - 74
        mapa(p, R, M, top, W - 2*M, mh2, sat, fetch, rango=(d0, d1), numeros=True)
        ly = _leyenda(p, top + mh2 + 16, saltos=R.get('acc', False))
        p.text(M, ly + 14, "T = trasluchada, V = virada, numeradas en orden de hora (completas y fallidas juntas); el color indica el resultado.", 6.8, False, GRIS)

    # ---------- resumen detallado y tabla de maniobras
    p.page(); y = 50
    if R.get('comentario'):
        p.text(M, y, "Comentario", 15, True, NAVY); y += 10
        lns = p.wrap(R['comentario'], 9.5, W - 2*M - 20)[:12]
        p.rect(M, y, W - 2*M, 12 + 13*len(lns), fill='#FFF8DB'); p.rect(M, y, 3, 12 + 13*len(lns), fill='#FFD400')
        for k, ln in enumerate(lns): p.text(M + 12, y + 15 + 13*k, ln, 9.5, False, '#222222')
        y += 12 + 13*len(lns) + 26
    p.text(M, y, "Resumen de la sesión", 15, True, NAVY); y += 6
    p.text(M, y + 8, "Cada dato con una explicación de qué es y para qué sirve.", 7.5, False, GRIS); y += 16
    def _md(x, d, suf): return _n(x, d, suf)
    def _sg(x): return 's/d' if x is None else (f"{x:+.0f} m".replace('+-', '-'))
    ANG = R.get('angulos') or {}
    filas = ([("Nombre de la sesión", R['nombre'])] if R.get('nombre') else []) + \
            ([("Tramo más largo sin caídas", f"{int(R['tramo_largo']['dur_s'] // 60)}:{int(round(R['tramo_largo']['dur_s'] % 60)):02d} min · {_n(R['tramo_largo']['dist_km'], 2, ' km')} · "
                                             f"{R['tramo_largo']['trasluchadas']} trasluchadas · {R['tramo_largo']['viradas']} viradas ({R['tramo_largo']['ini']}–{R['tramo_largo']['fin']})")] if R.get('tramo_largo') else []) + ([("Lugar", R['lugar'])] if R.get('lugar') else []) + \
            ([("Intensidad del viento", _n(R['viento_kn'], 1, ' kn'))] if R.get('viento_kn') is not None else []) + [("Disciplina", DISC), ("Origen del archivo", R['origen']), ("Dirección del viento (desde)", f"{R['viento']:.0f}°"),
             ("Distancia total recorrida", _n(R['distancia_km'], 2, ' km')), ("Tiempo total del recorrido", _n(R['tiempo_min'], 1, ' min'))] + \
            ([("Tiempo navegando (más de 4 nudos)", _n(R.get('nav_min'), 1, ' min')), ("% del tiempo navegando", _pct((R.get('nav_min') or 0) / R['tiempo_min'] if R['tiempo_min'] else None)),
              ("Velocidad media navegando (más de 4 nudos)", _n(R.get('vel_media_nav'), 2, ' kn'))] if WS else
             [("Tiempo total de planeo (>7 nudos)", _n(R['planeo_min'], 1, ' min')), ("% del tiempo planeando", _pct(R['planeo_pct'])),
              ("Velocidad media de navegación en planeo (>7 nudos)", _n(R['vel_media_planeo'], 2, ' kn'))]) + \
            [("Velocidad máxima en un tramo de 20 m", f"{_n(R['vmax20'], 2, ' kn')}  ({R['vmax20_hora']})"),
             ("Viradas completas / fallidas", f"{V['completas']} / {V['fallidas']}"), ("% de éxito en viradas", _pct(V['exito'])),
             ("Trasluchadas completas / fallidas", f"{T['completas']} / {T['fallidas']}"), ("% de éxito en trasluchadas", _pct(T['exito']))]
    for X, pl in ((T, 'trasluchadas'), (V, 'viradas')):
        filas += [(f"Velocidad promedio de entrada ({pl} completas)", _n(X['v_in'], 2, ' kn')), (f"Velocidad promedio de salida ({pl} completas)", _n(X['v_out'], 2, ' kn')),
                  (f"Variación promedio salida vs entrada ({pl} completas)", _pct(X['variacion'], True))]
        if 'vmin_med' in X:
            filas += [(f"Velocidad mínima en el giro ({pl} completas, mediana)", _md(X.get('vmin_med'), 1, ' kn')),
                      (f"Duración del giro ({pl} completas, mediana)", _md(X.get('dur_med'), 0, ' s')),
                      (f"Radio del giro ({pl} completas, mediana)", _md(X.get('radio_med'), 0, ' m')),
                      (f"Metros contra el viento en el giro ({pl} completas, mediana)", _sg(X.get('barlo_med'))),
                      (f"Tiempo para recuperar la velocidad ({pl} completas, mediana)", _md(X.get('t_rec_med'), 0, ' s'))]
            if not WS: filas += [(f"Maniobras sin bajar de 7 kn, en planeo ({pl})", f"{X.get('en_planeo', 0)}  ({_pct(X.get('en_planeo_pct'))})"),
                                 (f"Completas tocando el agua ({pl})", str(X.get('toques', 0)))]
    if ANG:
        for ld in ('babor', 'estribor'):
            a_ = ANG.get(ld, {})
            filas += [(f"Ángulo de ceñida, viento por {ld} (mediana)", _md(a_.get('cenida'), 0, '°')), (f"Ángulo en el largo, viento por {ld} (mediana)", _md(a_.get('largo'), 0, '°')),
                      (f"VMG medio contra el viento, viento por {ld}", _md(a_.get('vmg_up'), 2, ' kn')), (f"VMG medio a favor del viento, viento por {ld}", _md(a_.get('vmg_dn'), 2, ' kn'))]
        filas += [("Mejor VMG contra el viento (sostenido 10 s)", _md(R.get('vmg_up'), 2, ' kn') + (f"  ({R['vmg_up_hora']})" if R.get('vmg_up_hora') else '')),
                  ("Mejor VMG a favor del viento (sostenido 10 s)", _md(R.get('vmg_dn'), 2, ' kn') + (f"  ({R['vmg_dn_hora']})" if R.get('vmg_dn_hora') else ''))]
    filas += [("Cortes de señal GPS", str(R['cortes'])), ("Tiempo total sin señal", _n(R['sin_senal_min'], 1, ' min')),
              (f"Puntos descartados por precisión (> {R['max_acc']:g} m)", str(R['descartados_precision'])),
              ("Lecturas dudosas no usadas para la velocidad máxima", str(R.get('descartados_inestable', 0)))]
    if R.get('acc'):
        SL = R.get('saltos', []); top_ = max(SL, key=lambda e: e['altura']) if SL else None
        sc_ = sum(e['resultado'] == 'Completo' for e in SL)
        filas += [(f"Saltos (vuelo de {R['salto_min']:g} s o más y {R.get('salto_h_min', 0.5):g} m o más)".replace('.', ','), str(len(SL))),
                  ("Saltos completos / fallidos", f"{sc_} / {len(SL) - sc_}"),
                  ("% de éxito en saltos", _pct(sc_ / len(SL)) if SL else 's/d'),
                  ("Salto más alto", f"{_n(top_['altura'], 2, ' m')}  ({top_['hora']}, {top_['resultado'].lower()})" if top_ else 's/d')]
    else:
        filas += [("Saltos", "sin datos de acelerómetro")]
    EX = wf_textos.resumen(WS)
    for i, (l, v_) in enumerate(filas):
        ex = wf_textos.buscar(EX, l)
        lns = p.wrap(ex, 6.8, W - 2*M - 150) if ex else []
        hh = 15 + 8.4*len(lns) + (2 if lns else 0)
        if y + hh > H - 40: p.page(); y = 50
        if i % 2 == 0: p.rect(M, y, W - 2*M, hh, fill=CLARO)
        neg = v_.startswith('-') and v_.endswith('%')
        p.text(M + 6, y + 10.5, p.fit(l, 8.5, W - 2*M - 150, True), 8.5, True, '#222222')
        p.text(W - M - 6, y + 10.5, p.fit(v_, 8.5, 140, True), 8.5, True, '#C00000' if neg else NAVY, 'right')
        for k, ln in enumerate(lns): p.text(M + 6, y + 19.5 + 8.4*k, ln, 6.8, False, GRIS)
        y += hh
    y += 22
    cols = [("Mapa", 24, 'center'), ("Result.", 38, 'left'), ("Sec.", 20, 'center'), ("Hora", 38, 'center'),
            ("Vel. ent.", 33, 'right'), ("Vel. sal.", 33, 'right'), ("Var. vel.", 35, 'right'), ("Vel. mín.", 33, 'right'),
            ("Durac.", 29, 'right'), ("Radio", 29, 'right'), ("Barlo.", 31, 'right'), ("Recup.", 30, 'right'),
            ("Áng. ent.", 33, 'right'), ("Áng. sal.", 33, 'right'), ("Viento", 0, 'left')]
    used = sum(c[1] for c in cols); cols[-1] = (cols[-1][0], W - 2*M - used, 'left')
    def head(y):
        p.text(M, y, "Maniobras", 15, True, NAVY); y += 10
        p.rect(M, y, W - 2*M, 18, fill=NAVY); xx = M
        for nm, cw, al in cols:
            tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
            p.text(tx, y + 12, nm, 6.6, True, '#FFFFFF', al); xx += cw
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
            seccion = min(int(m['cd'] // sl) + 1, NS) if sl else 1
            _g = lambda x_, sg=False: 's/d' if x_ is None else (f"{x_:+.0f}°" if sg else f"{x_:.0f}°")
            vals = [str(m['n']), m['resultado'], str(seccion), m['hora'], _n(m['v_in'], 1), _n(m['v_out'], 1), _pct(m['variacion'], True),
                    _n(m.get('vmin'), 1) + ('*' if m.get('planeo') else ''), _n(m.get('dur'), 0, ' s'), _n(m.get('radio'), 0, ' m'),
                    's/d' if m.get('barlo') is None else f"{m['barlo']:+.0f} m".replace('+-', '-'), _n(m.get('t_rec'), 0, ' s'),
                    _g(m.get('ang_in')), _g(m.get('ang_out')), (m.get('amura') or 's/d') + (' · ' + m['nota'] if m['nota'] else '')]
            xx = M
            for (nm, cw, al), val in zip(cols, vals):
                tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
                col = '#C00000' if nm == 'Var. vel.' and val.startswith('-') else '#222222'
                p.text(tx, y + 10, p.fit(val, 7.2, cw - 5), 7.2, nm in ('Mapa', 'Result.'), col, al); xx += cw
            y += 14
        y += 14
        # glosario de columnas: qué es y para qué sirve cada una
        GL = wf_textos.maniobras(WS)
        abrev = {'Nombre / Mapa': 'Mapa', 'Resultado': 'Result.', 'Hora / Transcurrido': 'Hora', 'Vel. entrada': 'Vel. ent.', 'Vel. salida': 'Vel. sal.',
                 'Variación': 'Var. vel.', 'Vel. mínima': 'Vel. mín.' + ('' if WS else ' (* = en planeo)'), 'Duración': 'Durac.', 'Radio': 'Radio', 'Contra el viento': 'Barlo.',
                 'Recuperación': 'Recup.', 'Ángulo de entrada': 'Áng. ent.', 'Ángulo de salida': 'Áng. sal.', 'Viento por': 'Viento', 'Observación': 'Viento (nota)'}
        if y > H - 140: p.page(); y = 50
        p.text(M, y, "Qué es y para qué sirve cada columna", 11, True, NAVY); y += 12
        for k_, txt in GL:
            if k_ == 'En planeo': continue
            lab = abrev.get(k_, k_)
            lns = p.wrap(txt, 7, W - 2*M - 78)
            if y + 9.5*len(lns) > H - 40: p.page(); y = 50
            p.text(M, y, lab, 7, True, NAVY)
            for ln in lns: p.text(M + 78, y, ln, 7, False, GRIS); y += 9.5
            y += 2
    SL = R.get('saltos', [])
    if SL:
        y += 14
        if y > H - 120: p.page(); y = 50
        scols = [("Mapa", 28, 'center'), ("Resultado", 52, 'left'), ("Hora", 46, 'center'), ("Sec.", 24, 'center'), ("Vuelo", 40, 'right'),
                 ("Altura máx.", 50, 'right'), ("Distancia", 48, 'right'), ("Vel. kn", 38, 'right'), ("Después", 42, 'right'), ("Impacto", 40, 'right'), ("Observación", 0, 'left')]
        used = sum(c[1] for c in scols); scols[-1] = (scols[-1][0], W - 2*M - used, 'left')
        def shead(y):
            p.text(M, y, "Saltos", 15, True, NAVY); y += 10
            p.rect(M, y, W - 2*M, 18, fill=NAVY); xx = M
            for nm, cw, al in scols:
                tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
                p.text(tx, y + 12, nm, 7.3, True, '#FFFFFF', al); xx += cw
            return y + 18
        y = shead(y)
        for e in SL:
            if y > H - 50: p.page(); y = shead(50)
            p.rect(M, y, W - 2*M, 14, fill='#DFF9FF' if e['resultado'] == 'Completo' else '#FFD6EC')
            sec_ = min(int(e['cd'] // sl) + 1, NS) if sl else 1
            vals = ['S' + e['nombre'].split('#')[1].split(' ')[0], e['resultado'], e['hora'], str(sec_), _n(e['aire'], 2, ' s'), _n(e['altura'], 2, ' m'), _n(e.get('dist'), 1, ' m'),
                    _n(e['v_in'], 1), _n(e['v_out'], 1), _n(e['impacto_g'], 1, ' g'), e.get('nota', '')]
            xx = M
            for (nm, cw, al), val in zip(scols, vals):
                tx = xx + 5 if al == 'left' else xx + cw/2 if al == 'center' else xx + cw - 5
                p.text(tx, y + 10, p.fit(val, 7.6, cw - 6), 7.6, nm in ('Mapa', 'Altura máx.', 'Resultado'), '#222222', al); xx += cw
            y += 14
        y += 12
        if y < H - 50:
            for ln in p.wrap("Salto = el acelerómetro (teléfono en el pecho) marca menos de 0,7 g durante 1 s o más, con una altura estimada de 0,5 m o más (así el paso de una ola no cuenta como salto). Altura máx. = (g - tirón del ala) x t x t / 8, con t = tiempo en vuelo. 'Completo' = después del aterrizaje la velocidad sigue por encima de 4 nudos. 'Fallido' = en los 10 s posteriores la velocidad cae bajo 4 nudos por más de 5 s, o la señal GPS se corta más de 5 s (teléfono bajo el agua). Vuelo = tiempo en el aire. Distancia = velocidad GPS al despegar x tiempo en el aire. Después = velocidad media de 1 a 5 s después del aterrizaje.", 7, W - 2*M):
                p.text(M, y, ln, 7, False, GRIS); y += 9.5
    rendimiento(p, R)
    for i, c in enumerate(p.pages, 1):           # pie de página
        p.c = c; p.text(W/2, H - 18, f"Wingfoil & PW Tracker · Análisis {DISC} · {R['fecha']} · página {i} de {len(p.pages)}", 7, False, '#8899AA', 'center')
    p.save(path)

if __name__ == '__main__':
    informe(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2])
    print("PDF:", sys.argv[2])
