"""Prueba en GitHub: arma el PDF de una sesión sintética con imágenes satelitales reales."""
import sys, os, json, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'src', 'main', 'python'))
d_ = os.path.dirname(__file__)
os.system(f"{sys.executable} {os.path.join(d_, 'gen_test.py')} /tmp/test0.zip")
os.system(f"{sys.executable} {os.path.join(d_, 'gen_acc.py')} /tmp/test0.zip /tmp/test.zip")
os.makedirs('/tmp/sess', exist_ok=True); zipfile.ZipFile('/tmp/test.zip').extractall('/tmp/sess')
import runner
r = json.loads(runner.run('/tmp/sess', 'ci_out', 90, '30-10-2026', 3, '', True))
print(r.get('resumen') or r)
assert r['ok']
print(r['log'])
assert 'Saltos (vuelo >= 0.8 s): 3 | completos 2 | fallidos 1' in r['log']
