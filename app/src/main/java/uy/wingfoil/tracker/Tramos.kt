package uy.wingfoil.tracker

import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.tan

/**
 * Pantalla "Tramos a excluir": muestra el track sobre la foto satelital y un gráfico de velocidad.
 * La app propone las posibles salidas del agua (detectadas por wf_tramos.py) y se pueden marcar
 * tramos a mano tocando dos puntos en el mapa o en el gráfico.
 */
object Tramos {

    class Tramo(val ini: String, val fin: String, var marcado: Boolean, val detectado: Boolean, val info: String = "")

    private const val TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%d/%d/%d"
    private val BG = Color.rgb(6, 20, 38)
    private val CARD = Color.rgb(13, 35, 64)
    private val ACC = Color.rgb(0, 200, 255)
    private val MUT = Color.rgb(143, 169, 199)
    private val EXC = Color.rgb(255, 60, 90)
    private val SEL = Color.rgb(255, 160, 0)
    private val SPD = intArrayOf(Color.WHITE, Color.rgb(0, 216, 74), Color.rgb(255, 212, 0), Color.rgb(255, 45, 45))
    private fun bk(v: Double) = if (v < 4) 0 else if (v < 7) 1 else if (v < 12) 2 else 3

    /** Abre la pantalla. [actual] = texto del campo de tramos ("HH:MM:SS-HH:MM:SS, ..."). */
    fun abrir(act: Activity, dir: File, actual: String, onListo: (String) -> Unit) {
        val wait = AlertDialog.Builder(act).setTitle("Preparando el mapa…")
            .setMessage("Buscando posibles salidas del agua y cargando la foto satelital.").setCancelable(false).show()
        Thread {
            var err: String? = null
            var data: JSONObject? = null
            var mapa: Mapa? = null
            try {
                Analysis.ensurePython(act)
                data = JSONObject(Python.getInstance().getModule("wf_tramos").callAttr("preparar", dir.absolutePath).toString())
                if (!data.optBoolean("ok")) err = data.optString("error")
                else {
                    Tiles.cacheDir = File(act.filesDir, "tiles").apply { mkdirs() }; Tiles.reset()
                    mapa = Mapa.armar(data)
                }
            } catch (e: Throwable) { err = e.toString() }
            act.runOnUiThread {
                wait.dismiss()
                if (err != null || data == null || mapa == null) {
                    AlertDialog.Builder(act).setTitle("No se pudo abrir el mapa").setMessage(err ?: "Error desconocido")
                        .setPositiveButton("OK", null).show()
                } else mostrar(act, mapa, data, actual, onListo)
            }
        }.start()
    }

    /** Datos del track proyectados (Web Mercator, zoom z) + foto satelital armada con teselas. */
    class Mapa(val z: Int, val x: DoubleArray, val y: DoubleArray, val t: DoubleArray, val v: DoubleArray,
               val seg: IntArray, val hora: Array<String>, val foto: Bitmap?, val fx0: Double, val fy0: Double) {
        val n get() = x.size
        companion object {
            fun merc(lat: Double, lon: Double, z: Int): Pair<Double, Double> {
                val nn = 256.0 * (1 shl z)
                val la = max(-85.0, min(85.0, lat)) * PI / 180
                return Pair((lon + 180) / 360 * nn, (1 - ln(tan(la) + 1 / cos(la)) / PI) / 2 * nn)
            }

            fun armar(j: JSONObject): Mapa {
                val a = j.getJSONArray("puntos"); val n = a.length()
                val lat = DoubleArray(n); val lon = DoubleArray(n)
                val t = DoubleArray(n); val v = DoubleArray(n); val sg = IntArray(n); val h = Array(n) { "" }
                for (i in 0 until n) {
                    val p = a.getJSONArray(i)
                    t[i] = p.getDouble(0); lat[i] = p.getDouble(1); lon[i] = p.getDouble(2); v[i] = p.getDouble(3)
                    sg[i] = p.getInt(4); h[i] = p.getString(5)
                }
                // zoom: que el track entre en ~1600 px de ancho como máximo
                var z = 18
                while (z > 3) {
                    val (x0, y0) = merc(lat.max(), lon.min(), z); val (x1, y1) = merc(lat.min(), lon.max(), z)
                    if (x1 - x0 <= 1600 && y1 - y0 <= 1600) break
                    z--
                }
                val xs = DoubleArray(n); val ys = DoubleArray(n)
                for (i in 0 until n) { val (mx, my) = merc(lat[i], lon[i], z); xs[i] = mx; ys[i] = my }
                // foto: teselas que cubren el track con margen
                val padM = 0.25
                val bx0 = xs.min(); val bx1 = xs.max(); val by0 = ys.min(); val by1 = ys.max()
                val px = (bx1 - bx0) * padM + 60; val py = (by1 - by0) * padM + 60
                val tx0 = floor((bx0 - px) / 256).toInt(); val tx1 = floor((bx1 + px) / 256).toInt()
                val ty0 = floor((by0 - py) / 256).toInt(); val ty1 = floor((by1 + py) / 256).toInt()
                var foto: Bitmap? = null
                if ((tx1 - tx0 + 1) * (ty1 - ty0 + 1) <= 120) {
                    val bmp = Bitmap.createBitmap((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256, Bitmap.Config.RGB_565)
                    val c = Canvas(bmp); c.drawColor(Color.rgb(14, 42, 71))
                    var ok = 0
                    val nmax = 1 shl z
                    for (ty in ty0..ty1) for (tx in tx0..tx1) {
                        if (ty < 0 || ty >= nmax) continue
                        val b = Tiles.get(String.format(TILE_URL, z, ty, ((tx % nmax) + nmax) % nmax)) ?: continue
                        val tb = BitmapFactory.decodeByteArray(b, 0, b.size) ?: continue
                        c.drawBitmap(tb, ((tx - tx0) * 256).toFloat(), ((ty - ty0) * 256).toFloat(), null); tb.recycle(); ok++
                    }
                    if (ok > 0) foto = bmp else bmp.recycle()
                }
                return Mapa(z, xs, ys, t, v, sg, h, foto, tx0 * 256.0, ty0 * 256.0)
            }
        }

        fun idxDesde(hh: String): Int { for (i in 0 until n) if (hora[i] >= hh) return i; return n - 1 }
        fun idxHasta(hh: String): Int { for (i in n - 1 downTo 0) if (hora[i] <= hh) return i; return 0 }
    }

    /** Estado compartido entre el mapa, el gráfico y la lista. */
    class Estado(val m: Mapa) {
        val tramos = ArrayList<Tramo>()
        var a = -1; var b = -1
        var onCambio: () -> Unit = {}
        fun tocar(i: Int) {
            if (a < 0 || b >= 0) { a = i; b = -1 } else { b = i; if (b < a) { val k = a; a = b; b = k } }
            onCambio()
        }
        fun rangos(): List<Pair<Int, Int>> = tramos.filter { it.marcado }.map { Pair(m.idxDesde(it.ini), m.idxHasta(it.fin)) }
    }

    /* ---------------- mapa con zoom (pellizcar) y desplazamiento ---------------- */
    class MapaView(ctx: Context, val e: Estado) : View(ctx) {
        private val m = e.m
        private var esc = 1f; private var ox = 0f; private var oy = 0f; private var listo = false
        private val pLinea = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
        private val pPunto = Paint(Paint.ANTI_ALIAS_FLAG)
        private val dens = ctx.resources.displayMetrics.density
        private val sc = ScaleGestureDetector(ctx, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                val f = d.scaleFactor; val ns = max(0.3f, min(esc * f, 40f)); val k = ns / esc
                ox = d.focusX - (d.focusX - ox) * k; oy = d.focusY - (d.focusY - oy) * k; esc = ns; invalidate(); return true
            }
        })
        private val gd = GestureDetector(ctx, object : GestureDetector.SimpleOnGestureListener() {
            override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean { ox -= dx; oy -= dy; invalidate(); return true }
            override fun onSingleTapConfirmed(ev: MotionEvent): Boolean {
                var best = -1; var bd = Float.MAX_VALUE
                for (i in 0 until m.n) {
                    val dx = sx(i) - ev.x; val dy = sy(i) - ev.y; val d = dx * dx + dy * dy
                    if (d < bd) { bd = d; best = i }
                }
                if (best >= 0 && bd < (40 * dens) * (40 * dens)) e.tocar(best)
                return true
            }
            override fun onDoubleTap(ev: MotionEvent): Boolean { listo = false; invalidate(); return true }
        })

        private fun sx(i: Int) = (m.x[i] * esc + ox).toFloat()
        private fun sy(i: Int) = (m.y[i] * esc + oy).toFloat()

        override fun onTouchEvent(ev: MotionEvent): Boolean { sc.onTouchEvent(ev); if (!sc.isInProgress) gd.onTouchEvent(ev); return true }

        private fun encuadrar() {
            val x0 = m.x.min(); val x1 = m.x.max(); val y0 = m.y.min(); val y1 = m.y.max()
            val pad = 24 * dens
            esc = min((width - 2 * pad) / max(x1 - x0, 1.0), (height - 2 * pad) / max(y1 - y0, 1.0)).toFloat()
            ox = (width / 2f - ((x0 + x1) / 2 * esc).toFloat()); oy = (height / 2f - ((y0 + y1) / 2 * esc).toFloat())
            listo = true
        }

        override fun onDraw(c: Canvas) {
            if (!listo) encuadrar()
            c.drawColor(Color.rgb(14, 42, 71))
            m.foto?.let { f ->
                val l = (m.fx0 * esc + ox).toFloat(); val t = (m.fy0 * esc + oy).toFloat()
                c.drawBitmap(f, Rect(0, 0, f.width, f.height), RectF(l, t, l + f.width * esc, t + f.height * esc), null)
                c.drawColor(Color.argb(60, 0, 0, 0))
            }
            fun tramo(i0: Int, i1: Int, color: Int, w: Float) {
                pLinea.color = color; pLinea.strokeWidth = w * dens
                val p = Path(); var abierto = false
                for (i in i0..i1) {
                    if (!abierto || (i > i0 && m.seg[i] != m.seg[i - 1])) { p.moveTo(sx(i), sy(i)); abierto = true } else p.lineTo(sx(i), sy(i))
                }
                c.drawPath(p, pLinea)
            }
            for ((i0, i1) in e.rangos()) tramo(i0, i1, Color.argb(200, 255, 60, 90), 9f)
            if (e.a >= 0 && e.b >= 0) tramo(e.a, e.b, Color.argb(220, 255, 160, 0), 9f)
            // track por color de velocidad
            pLinea.strokeWidth = 2.2f * dens
            for (k in 0..3) {
                pLinea.color = SPD[k]
                val p = Path()
                for (i in 1 until m.n) {
                    if (m.seg[i] != m.seg[i - 1] || bk((m.v[i] + m.v[i - 1]) / 2) != k) continue
                    p.moveTo(sx(i - 1), sy(i - 1)); p.lineTo(sx(i), sy(i))
                }
                c.drawPath(p, pLinea)
            }
            for ((i, col) in listOf(Pair(e.a, Color.rgb(0, 220, 90)), Pair(e.b, EXC))) if (i >= 0) {
                pPunto.color = Color.BLACK; c.drawCircle(sx(i), sy(i), 9 * dens, pPunto)
                pPunto.color = col; c.drawCircle(sx(i), sy(i), 7 * dens, pPunto)
            }
        }
    }

    /* ---------------- gráfico de velocidad en el tiempo ---------------- */
    class GraficoView(ctx: Context, val e: Estado) : View(ctx) {
        private val m = e.m
        private val dens = ctx.resources.displayMetrics.density
        private val pL = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.4f * dens; color = ACC }
        private val pF = Paint()
        private val pT = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = MUT; textSize = 11 * dens }
        private val vmax = max(15.0, m.v.max())
        private fun gx(i: Int) = (pad() + (m.t[i] - m.t[0]) / max(m.t[m.n - 1] - m.t[0], 1.0) * (width - 2 * pad())).toFloat()
        private fun pad() = 8 * dens
        private fun gy(v: Double) = (height - 16 * dens - v / vmax * (height - 24 * dens)).toFloat()

        override fun onTouchEvent(ev: MotionEvent): Boolean {
            if (ev.action == MotionEvent.ACTION_UP) {
                var best = 0; var bd = Float.MAX_VALUE
                for (i in 0 until m.n) { val d = abs(gx(i) - ev.x); if (d < bd) { bd = d; best = i } }
                e.tocar(best)
            }
            return true
        }

        override fun onDraw(c: Canvas) {
            c.drawColor(CARD)
            fun banda(i0: Int, i1: Int, col: Int) { pF.color = col; c.drawRect(gx(i0), 0f, max(gx(i1), gx(i0) + 2), height.toFloat(), pF) }
            for ((i0, i1) in e.rangos()) banda(i0, i1, Color.argb(110, 255, 60, 90))
            if (e.a >= 0 && e.b >= 0) banda(e.a, e.b, Color.argb(120, 255, 160, 0))
            pF.color = Color.argb(70, 255, 255, 255)
            for (kn in listOf(4.0, 7.0, 12.0)) c.drawLine(pad(), gy(kn), width - pad(), gy(kn), pF)
            val p = Path()
            for (i in 0 until m.n) {
                if (i == 0 || m.seg[i] != m.seg[i - 1]) p.moveTo(gx(i), gy(m.v[i])) else p.lineTo(gx(i), gy(m.v[i]))
            }
            c.drawPath(p, pL)
            for ((i, col) in listOf(Pair(e.a, Color.rgb(0, 220, 90)), Pair(e.b, EXC))) if (i >= 0) {
                pF.color = col; c.drawRect(gx(i) - 1.5f * dens, 0f, gx(i) + 1.5f * dens, height.toFloat(), pF)
            }
            c.drawText(m.hora[0], pad(), height - 3 * dens, pT)
            val fin = m.hora[m.n - 1]; c.drawText(fin, width - pad() - pT.measureText(fin), height - 3 * dens, pT)
            c.drawText("7 kn", pad() + 2, gy(7.0) - 2, pT)
        }
    }

    private fun parse(txt: String): List<Pair<String, String>> =
        Regex("""(\d{1,2}:\d{2}:\d{2})-(\d{1,2}:\d{2}:\d{2})""").findAll(txt).map {
            Pair(it.groupValues[1].padStart(8, '0'), it.groupValues[2].padStart(8, '0'))
        }.toList()

    private fun dur(m: Mapa, a: Int, b: Int) = (m.t[b] - m.t[a]) / 60.0

    private fun mostrar(act: Activity, m: Mapa, data: JSONObject, actual: String, onListo: (String) -> Unit) {
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val e = Estado(m)
        val previos = parse(actual)
        val det = data.getJSONArray("detectados")
        for (k in 0 until det.length()) {
            val o = det.getJSONObject(k)
            val ini = o.getString("ini"); val fin = o.getString("fin")
            val ya = previos.any { it.first == ini && it.second == fin }
            e.tramos.add(Tramo(ini, fin, if (previos.isEmpty()) o.optBoolean("marcar", true) else ya, true,
                String.format("%.1f min · %.1f kn de media", o.getDouble("min"), o.getDouble("v")).replace('.', ',')))
        }
        for ((ini, fin) in previos) if (e.tramos.none { it.ini == ini && it.fin == fin }) e.tramos.add(Tramo(ini, fin, true, false))

        val dlg = Dialog(act, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(BG); setPadding(dp(10), dp(10), dp(10), dp(10)) }
        fun tv(s: String, size: Float, col: Int = Color.WHITE, bold: Boolean = false) = TextView(act).apply {
            text = s; textSize = size; setTextColor(col); if (bold) typeface = Typeface.DEFAULT_BOLD
        }
        root.addView(tv("Tramos a excluir", 20f, Color.WHITE, true))
        root.addView(tv("Tocá el mapa o el gráfico para marcar el inicio y después el fin de un tramo. Pellizcá para acercar; doble toque para volver a encuadrar.", 13f, MUT))
        val mapaV = MapaView(act, e)
        root.addView(mapaV, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f).apply { topMargin = dp(6) })
        val graf = GraficoView(act, e)
        root.addView(graf, LinearLayout.LayoutParams(MATCH_PARENT, dp(96)).apply { topMargin = dp(6) })
        val selInfo = tv("", 14f, SEL, true).apply { setPadding(0, dp(6), 0, 0) }
        root.addView(selInfo)
        val addB = Button(act).apply { text = "Agregar este tramo"; isAllCaps = false; setBackgroundColor(SEL); setTextColor(Color.BLACK); isEnabled = false }
        root.addView(addB, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(4) })
        val lista = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        root.addView(ScrollView(act).apply { addView(lista) }, LinearLayout.LayoutParams(MATCH_PARENT, dp(130)).apply { topMargin = dp(6) })
        val fila = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
        val cancel = Button(act).apply { text = "Cancelar"; isAllCaps = false }
        val ok = Button(act).apply { text = "Listo"; isAllCaps = false; setBackgroundColor(ACC); setTextColor(Color.BLACK) }
        fila.addView(cancel, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        fila.addView(ok, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { leftMargin = dp(8) })
        root.addView(fila, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(6) })

        fun armarLista() {
            lista.removeAllViews()
            if (e.tramos.isEmpty()) lista.addView(tv("No se detectaron salidas del agua. Si hubo alguna, marcala en el mapa o en el gráfico.", 13f, MUT))
            for (tr in e.tramos) {
                val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                val cb = CheckBox(act).apply {
                    text = "${tr.ini} – ${tr.fin}" + (if (tr.detectado) "  (detectado: ${tr.info})" else "  (marcado a mano)")
                    setTextColor(Color.WHITE); textSize = 13f; isChecked = tr.marcado
                    setOnCheckedChangeListener { _, ch -> tr.marcado = ch; mapaV.invalidate(); graf.invalidate() }
                }
                r.addView(cb, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
                r.addView(tv("ver", 13f, ACC, true).apply {
                    setPadding(dp(10), dp(8), dp(6), dp(8))
                    setOnClickListener { e.a = m.idxDesde(tr.ini); e.b = m.idxHasta(tr.fin); e.onCambio() }
                })
                if (!tr.detectado) r.addView(tv("quitar", 13f, EXC, true).apply {
                    setPadding(dp(8), dp(8), dp(4), dp(8))
                    setOnClickListener { e.tramos.remove(tr); armarLista(); mapaV.invalidate(); graf.invalidate() }
                })
                lista.addView(r)
            }
        }
        e.onCambio = {
            selInfo.text = when {
                e.a >= 0 && e.b >= 0 -> String.format("Inicio %s · Fin %s · %.1f min", m.hora[e.a], m.hora[e.b], dur(m, e.a, e.b)).replace('.', ',')
                e.a >= 0 -> "Inicio ${m.hora[e.a]} · ahora tocá el fin"
                else -> ""
            }
            addB.isEnabled = e.a >= 0 && e.b > e.a
            mapaV.invalidate(); graf.invalidate()
        }
        addB.setOnClickListener {
            if (e.a >= 0 && e.b > e.a) {
                e.tramos.add(Tramo(m.hora[e.a], m.hora[e.b], true, false)); e.a = -1; e.b = -1
                armarLista(); e.onCambio()
            }
        }
        cancel.setOnClickListener { dlg.dismiss() }
        ok.setOnClickListener {
            onListo(e.tramos.filter { it.marcado }.joinToString(", ") { "${it.ini}-${it.fin}" })
            dlg.dismiss()
        }
        armarLista(); e.onCambio()
        dlg.setContentView(root)
        dlg.setOnDismissListener { m.foto?.recycle() }
        dlg.show()
    }
}
