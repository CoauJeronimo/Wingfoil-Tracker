"""Descarga las imágenes satelitales listadas en tiles_needed.txt y las empaqueta en tiles.zip (las usa el PDF)."""
import hashlib, urllib.request, zipfile, os, sys, time
urls = [u.strip() for u in open(os.path.join(os.path.dirname(__file__), 'tiles_needed.txt')) if u.strip()]
ok = 0
with zipfile.ZipFile('tiles.zip', 'w') as z:
    for u in urls:
        for intento in range(3):
            try:
                rq = urllib.request.Request(u, headers={'User-Agent': 'WingfoilTracker/1.13 (prueba PDF)'})
                d = urllib.request.urlopen(rq, timeout=20).read()
                z.writestr(hashlib.sha1(u.encode()).hexdigest() + '.jpg', d); ok += 1; break
            except Exception as e:
                time.sleep(1)
print(f"{ok}/{len(urls)} imágenes")
sys.exit(0 if ok else 1)
