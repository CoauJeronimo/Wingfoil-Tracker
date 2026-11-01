"""Agrega TotalAcceleration.csv (100 Hz) a la sesión sintética: 2 saltos y 1 caída desde el aire."""
import zipfile, io, csv, random, math, sys
random.seed(2)
src, dst = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src); loc = z.read('Location.csv').decode(); meta = z.read('Metadata.csv').decode()
rows = list(csv.DictReader(io.StringIO(loc)))
EP = int(list(csv.DictReader(io.StringIO(meta)))[0]['recording epoch time'])
ts = [float(r['seconds_elapsed']) for r in rows]
# caída: justo antes del hueco grande de GPS
gap_i = max(range(1, len(ts)), key=lambda i: ts[i]-ts[i-1]); t_caida = ts[gap_i-1] - 5.5
eventos = [(100.0, 1.2, 3.5), (250.0, 1.5, 4.0), (t_caida, 1.1, 3.0)]   # (inicio, tiempo en el aire, |a| en el aire)
out = io.StringIO(); out.write('time,seconds_elapsed,z,y,x\n')
t = 0.0; T = ts[-1]
while t < T:
    a = 9.81 + random.gauss(0, 1.2); imp = 0
    for t0, d, aa in eventos:
        if t0 <= t <= t0 + d: a = aa + random.gauss(0, 0.4)
        if t0 + d < t <= t0 + d + 0.08: a = 35
    ang = random.uniform(0, 0.3)
    zz, yy, xx = a*math.cos(ang), a*math.sin(ang)*0.7, a*math.sin(ang)*0.7
    out.write(f"{int((EP/1000 + t)*1e9)},{t:.3f},{zz:.4f},{yy:.4f},{xx:.4f}\n")
    t += 0.01
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as w:
    w.writestr('Location.csv', loc); w.writestr('Metadata.csv', meta); w.writestr('TotalAcceleration.csv', out.getvalue())
print('eventos', eventos)
