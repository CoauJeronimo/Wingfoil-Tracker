"""Genera una sesión sintética de Wingfoil Tracker (zip) para probar el análisis.
Viento desde 90° (este). Bordes al norte/sur a ~14 kn, trasluchadas (giro por el oeste),
viradas (giro por el este), una trasluchada fallida seguida de 90 s sin señal."""
import math, random, zipfile, io, sys
random.seed(1)
K = 1.9438444924406
lat, lon = -34.65, -54.18
t = 0.0
EP = 1793400000000  # ms
rows = []
hdg = 0.0
def step(speed_kn, hdg_deg, acc=3.0, dt=1.0, record=True):
    global lat, lon, t
    v = speed_kn / K
    d = v * dt
    lat += d * math.cos(math.radians(hdg_deg)) / 111320
    lon += d * math.sin(math.radians(hdg_deg)) / (111320 * math.cos(math.radians(lat)))
    t += dt
    if record:
        rows.append((t, lat + random.gauss(0, 3e-6), lon + random.gauss(0, 3e-6), max(0, v + random.gauss(0, 0.1)), acc))
# arranque lento
for _ in range(20): step(2, 0)
for _ in range(10): step(8, 0)
def straight(n, h, sp=14):
    for _ in range(n): step(sp + random.gauss(0, 0.5), h)
def turn(h0, h1, direction, n=8, sp=10):
    # direction -1 = giro antihorario
    span = ((h1 - h0) * direction) % 360
    for i in range(1, n + 1): step(sp, (h0 + direction * span * i / n) % 360)
h = 0
for k in range(6):
    straight(60, h)
    if k % 3 == 2:
        # virada: pasa por 90 (proa al viento)
        nh = 180 if h == 0 else 0
        turn(h, nh, +1 if h == 0 else -1)
    else:
        nh = 180 if h == 0 else 0
        turn(h, nh, -1 if h == 0 else +1)   # trasluchada por 270
    h = nh
straight(60, h)
# trasluchada fallida + bajo el agua 90 s
nh = 180 if h == 0 else 0
turn(h, nh, -1 if h == 0 else +1)
for _ in range(3): step(2, nh)
for _ in range(90): step(0.5, nh, record=False)   # sin puntos
for _ in range(4): step(1, nh, acc=18)            # recuperación imprecisa (se filtra)
for _ in range(10): step(1, nh)
h = nh
straight(80, h)
turn(h, 180 if h == 0 else 0, -1 if h == 0 else +1)
h = 180 if h == 0 else 0
straight(60, h)
for _ in range(15): step(2, h)

buf = io.StringIO()
buf.write('time,seconds_elapsed,bearingAccuracy,speedAccuracy,verticalAccuracy,horizontalAccuracy,speed,bearing,altitude,longitude,latitude\n')
for tt, la, lo, sp, ac in rows:
    buf.write(f"{int((EP + tt*1000)*1e6)},{tt:.3f},,0.5,10.0,{ac:.2f},{sp:.4f},,1.0,{lo:.8f},{la:.8f}\n")
meta = ('version,device name,recording epoch time,recording time,recording timezone,platform,appVersion,device id,sensors,sampleRateMs,standardisation\n'
        f'3,Test,{EP},2026-10-30_10-00-00,America/Montevideo,android,WingfoilTracker-Android-1.0,WingFoil_test,Location,1000,false\n')
with zipfile.ZipFile(sys.argv[1], 'w') as z:
    z.writestr('Location.csv', buf.getvalue()); z.writestr('Metadata.csv', meta)
print(len(rows), 'puntos')
