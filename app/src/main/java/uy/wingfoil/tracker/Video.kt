package uy.wingfoil.tracker

import android.app.Activity
import android.app.AlertDialog
import android.content.ContentValues
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.view.Surface
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import java.util.Locale
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.tan

/**
 * Video de la sesión (estilo Relive): cámara inclinada (como un drone, ~50° desde la vertical) que sigue el
 * recorrido sobre la foto satelital y da una vuelta completa (360°) alrededor del cursor a lo largo del video,
 * el trazo se pinta con los colores de velocidad y en pantalla van la distancia recorrida, la
 * velocidad máxima (20 m) alcanzada hasta el momento y, al final, la velocidad media en planeo.
 * Dura 35-60 s según el tiempo navegado, H.264, sin audio. Se arma en el teléfono con MediaCodec.
 */
object Video {
    private const val TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%d/%d/%d"
    private const val FPS = 30
    private const val T_INTRO = 5.0            // paneo 360° del área antes de arrancar
    private const val T_OUTRO = 5.0            // paneo 360° del área al terminar
    // recorrido animado: 0,4 s por minuto de navegación, entre 25 y 50 s (video total 35-60 s)
    private fun durAnimPara(segActivos: Double) = max(25.0, min(50.0, 0.4 * segActivos / 60.0))
    private val SPD = intArrayOf(Color.WHITE, Color.rgb(0, 216, 74), Color.rgb(255, 212, 0), Color.rgb(255, 45, 45))
    private fun bk(v: Double) = if (v < 4) 0 else if (v < 7) 1 else if (v < 12) 2 else 3

    fun iniciar(act: Activity, dir: File) {
        val ops = arrayOf("Vertical 9:16 (historias de Instagram / WhatsApp)", "Horizontal 16:9")
        AlertDialog.Builder(act).setTitle("Video de la sesión (35-60 s según la duración)")
            .setItems(ops) { _, w -> generar(act, dir, w == 0) }
            .setNegativeButton("Cancelar", null).show()
    }

    private fun generar(act: Activity, dir: File, vertical: Boolean) {
        val wait = AlertDialog.Builder(act).setTitle("Generando video…").setMessage("Preparando el recorrido…").setCancelable(false).show()
        fun msg(s: String) = act.runOnUiThread { wait.setMessage(s) }
        Thread {
            var err: String? = null; var uri: Uri? = null
            try {
                uri = render(act, dir, vertical, ::msg)
            } catch (e: Throwable) { err = e.toString() }
            act.runOnUiThread {
                wait.dismiss()
                if (err != null || uri == null) {
                    AlertDialog.Builder(act).setTitle("No se pudo generar el video").setMessage(err ?: "Error desconocido")
                        .setPositiveButton("OK", null).show()
                } else {
                    val u = uri!!
                    // videos anteriores que Android no dejó borrar solo (guardados por otra instalación): se pide permiso
                    SessionInfo.pedirBorrado(act, viejos); viejos = emptyList()
                    AlertDialog.Builder(act).setTitle("Video listo")
                        .setMessage("Quedó guardado en Descargas/WingFoil (reemplaza al video anterior de esta sesión)." + if (sinFoto) "\n\nNo se pudo bajar la foto satelital (sin conexión a internet o sin imágenes de esa zona): el video salió con fondo liso." else "")
                        .setPositiveButton("Ver") { _, _ ->
                            try { act.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(u, "video/mp4").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) } catch (_: Exception) { }
                        }
                        .setNeutralButton("Compartir") { _, _ ->
                            act.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("video/mp4")
                                .putExtra(Intent.EXTRA_STREAM, u).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Compartir video"))
                        }
                        .setNegativeButton("Cerrar", null).show()
                }
            }
        }.start()
    }

    @Volatile private var sinFoto = false
    @Volatile private var viejos: List<Uri> = emptyList()

    /** Las zonas sin imágenes devuelven una tesela gris con el texto "Map data not yet available": se descarta. */
    private fun esFoto(b: ByteArray): Boolean {
        val o = BitmapFactory.Options().apply { inSampleSize = 8 }
        val bm = BitmapFactory.decodeByteArray(b, 0, b.size, o) ?: return false
        var gris = 0; var tot = 0
        for (y in 0 until bm.height step 2) for (x in 0 until bm.width step 2) {
            val c = bm.getPixel(x, y); val r = Color.red(c); val g = Color.green(c); val bl = Color.blue(c)
            val mx = max(r, max(g, bl)); val mn = min(r, min(g, bl))
            if (mx - mn < 10 && mx > 150) gris++
            tot++
        }
        bm.recycle()
        return tot == 0 || gris < tot * 0.85
    }

    private fun merc(lat: Double, lon: Double, z: Int): DoubleArray {
        val nn = 256.0 * (1 shl z)
        val la = max(-85.0, min(85.0, lat)) * PI / 180
        return doubleArrayOf((lon + 180) / 360 * nn, (1 - ln(tan(la) + 1 / cos(la)) / PI) / 2 * nn)
    }

    private val pBrF = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(150, 0, 0, 0) }
    private val pBrA = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.STROKE }
    private val pBrN = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(230, 40, 40) }
    private val pBrS = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val pBrT = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; typeface = Typeface.DEFAULT_BOLD; textAlign = Paint.Align.CENTER }

    /** Brújula: círculo con aguja roja hacia el norte (N) y blanca hacia el sur (S); ang = dirección del norte en pantalla (rad). */
    private fun brujula(c: Canvas, cx: Float, cy: Float, r: Float, ang: Double, u: Float) {
        c.drawCircle(cx, cy, r, pBrF)
        pBrA.strokeWidth = 3 * u; c.drawCircle(cx, cy, r - 4 * u, pBrA)
        val dx = cos(ang).toFloat(); val dy = Math.sin(ang).toFloat()        // hacia el norte
        val px = -dy; val py = dx                                            // perpendicular
        val L = r * 0.62f; val A = r * 0.17f
        val pN = android.graphics.Path().apply { moveTo(cx + dx * L, cy + dy * L); lineTo(cx + px * A, cy + py * A); lineTo(cx - px * A, cy - py * A); close() }
        val pS = android.graphics.Path().apply { moveTo(cx - dx * L, cy - dy * L); lineTo(cx + px * A, cy + py * A); lineTo(cx - px * A, cy - py * A); close() }
        c.drawPath(pS, pBrS); c.drawPath(pN, pBrN)
        c.drawCircle(cx, cy, 5 * u, pBrF)
        pBrT.textSize = 26 * u
        val rt = r * 0.84f
        pBrT.color = Color.rgb(255, 80, 80); c.drawText("N", cx + dx * rt, cy + dy * rt + 9 * u, pBrT)
        pBrT.color = Color.WHITE; c.drawText("S", cx - dx * rt, cy - dy * rt + 9 * u, pBrT)
    }

    private fun render(act: Activity, dir: File, vertical: Boolean, msg: (String) -> Unit): Uri {
        // ---------- datos: misma limpieza que el análisis; se saltean los tramos excluidos del último análisis
        Analysis.ensurePython(act)
        val j = JSONObject(Python.getInstance().getModule("wf_tramos").callAttr("preparar", dir.absolutePath).toString())
        if (!j.optBoolean("ok")) throw Exception(j.optString("error"))
        val excl = ArrayList<Pair<String, String>>()
        try {
            val r = JSONObject(File(dir, "analisis/resultados.json").readText()).optJSONArray("excluidos")
            if (r != null) for (k in 0 until r.length()) { val a = r.getJSONArray(k); excl.add(Pair(a.getString(0), a.getString(1))) }
        } catch (_: Exception) { }
        val a = j.getJSONArray("puntos")
        val lat = ArrayList<Double>(); val lon = ArrayList<Double>(); val t = ArrayList<Double>(); val v = ArrayList<Double>(); val sg = ArrayList<Int>(); val dud = ArrayList<Int>()
        var segExtra = 0; var antesExcl = false
        for (i in 0 until a.length()) {
            val p = a.getJSONArray(i); val h = p.getString(5)
            if (excl.any { h >= it.first && h <= it.second }) { antesExcl = true; continue }
            if (antesExcl) { segExtra += 1000; antesExcl = false }
            t.add(p.getDouble(0)); lat.add(p.getDouble(1)); lon.add(p.getDouble(2)); v.add(p.getDouble(3)); sg.add(p.getInt(4) + segExtra); dud.add(if (p.length() > 6) p.getInt(6) else 0)
        }
        val n = t.size
        if (n < 10) throw Exception("La sesión no tiene suficientes puntos para el video.")
        val W = if (vertical) 1080 else 1920; val H = if (vertical) 1920 else 1080
        val corto = min(W, H)

        // tiempo "activo" acumulado (sin huecos) y distancia acumulada
        val act_ = DoubleArray(n); val dist = DoubleArray(n)
        val kx = cos(lat[0] * PI / 180) * 111320.0; val ky = 110574.0
        for (i in 1 until n) {
            val mismo = sg[i] == sg[i - 1]
            act_[i] = act_[i - 1] + if (mismo) t[i] - t[i - 1] else 0.0
            dist[i] = dist[i - 1] + if (mismo) hypot((lon[i] - lon[i - 1]) * kx, (lat[i] - lat[i - 1]) * ky) else 0.0
        }
        val totAct = max(act_[n - 1], 1.0)
        // velocidad máxima en 20 m (mismo cálculo que el análisis), como máximo acumulado hasta cada punto
        val vmaxHasta = DoubleArray(n)
        run {
            val ps = DoubleArray(n + 1); for (i in 0 until n) ps[i + 1] = ps[i] + v[i]
            val pd = IntArray(n + 1); for (i in 0 until n) pd[i + 1] = pd[i] + dud[i]   // lecturas dudosas: no cuentan para la máxima
            var k2 = 0
            for (i0 in 0 until n) {
                k2 = max(k2, i0)
                if (k2 > i0 && sg[k2] != sg[i0]) k2 = i0
                while (k2 + 1 < n && sg[k2 + 1] == sg[i0] && dist[k2] - dist[i0] < 20) k2++
                if (dist[k2] - dist[i0] >= 20 && pd[k2 + 1] == pd[i0]) { val m_ = (ps[k2 + 1] - ps[i0]) / (k2 - i0 + 1); if (m_ > vmaxHasta[k2]) vmaxHasta[k2] = m_ }
            }
            for (i in 1 until n) vmaxHasta[i] = max(vmaxHasta[i], vmaxHasta[i - 1])
        }
        // velocidad media de navegación en planeo (> 7 kn), igual que el análisis
        // windsurf: el planeo no importa; al final va la velocidad media navegando (> 4 kn)
        val windsurf = SessionInfo.get(dir, "disciplina") == "windsurf"
        val vUmbral = if (windsurf) 4.0 else 7.0
        var tPlan = 0.0; var tvPlan = 0.0
        for (i in 1 until n) if (sg[i] == sg[i - 1]) { val vm = (v[i] + v[i - 1]) / 2; if (vm > vUmbral) { val dt = t[i] - t[i - 1]; tPlan += dt; tvPlan += dt * vm } }
        val vPlaneo = if (tPlan > 0) tvPlan / tPlan else 0.0
        val DUR_ANIM = durAnimPara(totAct)
        val DUR_TOTAL = T_INTRO + DUR_ANIM + T_OUTRO

        // ---------- encuadre: lo más cerca posible, pero que el cursor no cruce la pantalla en menos de ~1 s de video
        var latMin = lat.min(); var latMax = lat.max(); var lonMin = lon.min(); var lonMax = lon.max()
        val anchoM = (lonMax - lonMin) * kx; val altoM = (latMax - latMin) * ky
        val mPorSegVideo = dist[n - 1] / DUR_ANIM
        // lado corto de la vista a la altura del cursor: al menos 650 m (se ven la costa, los cabos, etc.);
        // en sesiones muy largas se abre más para que el cursor no cruce la pantalla de golpe
        val vistaM = max(650.0, 1.05 * mPorSegVideo)
        val vistaLargoM = vistaM * max(W, H) / corto
        // zoom de teselas: el mayor (≤ 18) sin pasar de ~300 teselas
        val mx = (vistaLargoM / 2) / kx; val my = (vistaLargoM / 2) / ky
        latMin -= my; latMax += my; lonMin -= mx; lonMax += mx
        var z = 18
        while (z > 10) {
            val p0 = merc(latMax, lonMin, z); val p1 = merc(latMin, lonMax, z)
            val nt = (floor(p1[0] / 256) - floor(p0[0] / 256) + 1) * (floor(p1[1] / 256) - floor(p0[1] / 256) + 1)
            if (nt <= 300) break
            z--
        }
        // hay zonas sin imágenes de alta resolución: se prueba la tesela del centro y se baja el zoom hasta encontrar foto real
        msg("Buscando la foto satelital de la zona…")
        Tiles.cacheDir = File(act.filesDir, "tiles").apply { mkdirs() }; Tiles.reset()
        run {
            val cLat = (latMin + latMax) / 2; val cLon = (lonMin + lonMax) / 2
            var zz = z
            while (zz >= max(10, z - 5)) {
                val m = merc(cLat, cLon, zz); val nn = 1 shl zz
                val b = Tiles.get(String.format(Locale.US, TILE_URL, zz, floor(m[1] / 256).toInt(), ((floor(m[0] / 256).toInt() % nn) + nn) % nn))
                if (b != null && esFoto(b)) { z = zz; break }
                if (Tiles.sinRed()) break
                zz--
            }
        }
        val X = DoubleArray(n); val Y = DoubleArray(n)
        for (i in 0 until n) { val m = merc(lat[i], lon[i], z); X[i] = m[0]; Y[i] = m[1] }
        val mPorPx = 156543.03392 * cos(lat[0] * PI / 180) / (1 shl z)
        val esc = (corto / (vistaM / mPorPx)).toFloat()                 // px de pantalla por px de mundo

        // ---------- teselas satelitales
        msg("Descargando la foto satelital…")
        val p0 = merc(latMax, lonMin, z); val p1 = merc(latMin, lonMax, z)
        val tx0 = floor(p0[0] / 256).toInt(); val tx1 = floor(p1[0] / 256).toInt()
        val ty0 = floor(p0[1] / 256).toInt(); val ty1 = floor(p1[1] / 256).toInt()
        // coordenadas relativas al borde de las teselas (en float, valores chicos = sin temblequeo)
        val OX = tx0 * 256.0; val OY = ty0 * 256.0
        for (i in 0 until n) { X[i] -= OX; Y[i] -= OY }
        val tiles = HashMap<Long, Bitmap>()
        val opt = BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.RGB_565 }
        val nmax = 1 shl z
        for (ty in ty0..ty1) for (tx in tx0..tx1) {
            if (ty < 0 || ty >= nmax) continue
            val b = Tiles.get(String.format(Locale.US, TILE_URL, z, ty, ((tx % nmax) + nmax) % nmax)) ?: continue
            if (!esFoto(b)) continue
            BitmapFactory.decodeByteArray(b, 0, b.size, opt)?.let { tiles[tx.toLong() * 100000L + ty] = it }
        }
        // fondo lejano de menor resolución (lo que se ve hacia el horizonte con la cámara inclinada)
        val zb = max(8, z - 4); val fac = 1 shl (z - zb); val nb = 1 shl zb
        val margenM = 6000.0
        val q0 = merc(latMax + margenM / ky, lonMin - margenM / kx, zb); val q1 = merc(latMin - margenM / ky, lonMax + margenM / kx, zb)
        val bx0 = floor(q0[0] / 256).toInt(); val bx1 = floor(q1[0] / 256).toInt(); val by0 = floor(q0[1] / 256).toInt(); val by1 = floor(q1[1] / 256).toInt()
        val fondo = ArrayList<Pair<RectF, Bitmap>>()
        if ((bx1 - bx0 + 1) * (by1 - by0 + 1) <= 64) for (ty in by0..by1) for (tx in bx0..bx1) {
            if (ty < 0 || ty >= nb) continue
            val b = Tiles.get(String.format(Locale.US, TILE_URL, zb, ty, ((tx % nb) + nb) % nb)) ?: continue
            if (!esFoto(b)) continue
            val bm = BitmapFactory.decodeByteArray(b, 0, b.size, opt) ?: continue
            val l = (tx * 256.0 * fac - tx0 * 256.0).toFloat(); val t_ = (ty * 256.0 * fac - ty0 * 256.0).toFloat(); val sz = (256.0 * fac).toFloat()
            fondo.add(Pair(RectF(l, t_, l + sz + fac, t_ + sz + fac), bm))
        }

        // ---------- codificador H.264 con superficie de entrada
        val tmp = File(act.cacheDir, "video_tmp.mp4"); tmp.delete()
        val fmt = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, W, H).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, if (vertical) 10_000_000 else 10_000_000)
            setInteger(MediaFormat.KEY_FRAME_RATE, FPS)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
            setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel41)
        }
        val enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        try { enc.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE) } catch (e: Exception) {
            fmt.removeKey(MediaFormat.KEY_PROFILE); fmt.removeKey(MediaFormat.KEY_LEVEL)
            enc.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        }
        val surf: Surface = enc.createInputSurface()
        enc.start()
        val mux = MediaMuxer(tmp.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        var track = -1; var muxOn = false; var salidos = 0L
        val info = MediaCodec.BufferInfo()
        fun drenar(fin: Boolean) {
            while (true) {
                val idx = enc.dequeueOutputBuffer(info, if (fin) 10_000 else 0)
                if (idx == MediaCodec.INFO_TRY_AGAIN_LATER) { if (!fin) return else continue }
                if (idx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) { track = mux.addTrack(enc.outputFormat); mux.start(); muxOn = true; continue }
                if (idx < 0) continue
                val buf = enc.getOutputBuffer(idx)!!
                if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) info.size = 0
                if (info.size > 0 && muxOn) {
                    info.presentationTimeUs = salidos * 1_000_000L / FPS; salidos++      // tiempos exactos, cuadro a cuadro
                    buf.position(info.offset); buf.limit(info.offset + info.size)
                    mux.writeSampleData(track, buf, info)
                }
                val eos = info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                enc.releaseOutputBuffer(idx, false)
                if (eos) return
            }
        }

        // ---------- dibujo
        val trazo = Array(4) { Path() }
        val pTrazo = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
        val pSombra = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND; color = Color.argb(110, 0, 0, 0) }
        val pBmp = Paint(Paint.FILTER_BITMAP_FLAG)
        val pPunto = Paint(Paint.ANTI_ALIAS_FLAG)
        val pCaja = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(150, 0, 0, 0) }
        val u = corto / 1080f
        val pVel = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 96 * u; typeface = Typeface.DEFAULT_BOLD }
        val pUni = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(220, 230, 240); textSize = 40 * u; typeface = Typeface.DEFAULT_BOLD }
        val pDist = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 44 * u; typeface = Typeface.DEFAULT_BOLD }
        val pPlan = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(0, 216, 74); textSize = 44 * u; typeface = Typeface.DEFAULT_BOLD }
        // ---------- cámara en perspectiva: plano (px de pantalla vistos desde arriba, origen = cámara) -> pantalla
        val PHI = 40.0                                  // inclinación del eje óptico bajo el horizonte (50° desde la vertical)
        val Fp = 0.96 * H; val bajo = 0.16 * H          // distancia focal; el cursor queda un poco abajo del centro
        val phiC = PHI + Math.toDegrees(Math.atan(bajo / Fp))
        val rr = Fp / cos(Math.toRadians(phiC - PHI)); val hh = rr * Math.sin(Math.toRadians(phiC)); val dd0 = rr * cos(Math.toRadians(phiC))
        fun proy(x: Double, py: Double): FloatArray {
            val f_ = dd0 - py; val pr = Math.toRadians(PHI)
            val zz = f_ * cos(pr) + hh * Math.sin(pr); val uu = f_ * Math.sin(pr) - hh * cos(pr)
            return floatArrayOf((W / 2 + Fp * x / zz).toFloat(), (H / 2 - Fp * uu / zz).toFloat())
        }
        val persp = Matrix()
        run {
            val A = W.toDouble(); val far = 3.0 * H
            val src = floatArrayOf((-A).toFloat(), 0f, A.toFloat(), 0f, A.toFloat(), (-far).toFloat(), (-A).toFloat(), (-far).toFloat())
            val q = listOf(proy(-A, 0.0), proy(A, 0.0), proy(A, -far), proy(-A, -far))
            val dst = floatArrayOf(q[0][0], q[0][1], q[1][0], q[1][1], q[2][0], q[2][1], q[3][0], q[3][1])
            persp.setPolyToPoly(src, 0, dst, 0, 4)
        }
        val cielo = Paint().apply {
            shader = LinearGradient(0f, 0f, 0f, H * 0.34f, intArrayOf(Color.rgb(150, 190, 220), Color.argb(170, 150, 190, 220), Color.argb(0, 150, 190, 220)),
                floatArrayOf(0f, 0.45f, 1f), Shader.TileMode.CLAMP)
        }
        val pSomb = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(120, 0, 0, 0) }
        val pPalo = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(200, 255, 255, 255); strokeWidth = 4 * (corto / 1080f) }
        // rumbo inicial de la cámara: a lo largo del lado más largo de la zona; después gira 90° en todo el video
        val th0 = if (anchoM > altoM) 0.0 else 90.0
        val pt = FloatArray(2)
        var hecho = 0                                  // último índice ya agregado al trazo
        var camX = X[0]; var camY = Y[0]
        val tau = 0.18                                 // suavizado de la cámara (s de video): bien pegada al cursor, que es el centro del giro
        val total = (DUR_TOTAL * FPS).toInt()
        // paneo del área: centro de la zona y vista amplia que la abarca entera
        val acX = (X.min() + X.max()) / 2; val acY = (Y.min() + Y.max()) / 2
        val escAmplio = min(esc.toDouble(), corto / (max(anchoM, altoM) * 1.3 / mPorPx)).toFloat()
        fun suave(x: Double): Double { val c_ = min(1.0, max(0.0, x)); return c_ * c_ * (3 - 2 * c_) }
        val tFin = T_INTRO + DUR_ANIM
        var camFinX = 0.0; var camFinY = 0.0
        fun busca(ta: Double): Int { var lo = 0; var hi = n - 1; while (hi - lo > 1) { val m = (lo + hi) / 2; if (act_[m] <= ta) lo = m else hi = m }; return lo }
        for (f in 0 until total) {
            val tv = f.toDouble() / FPS
            val ta = totAct * min(1.0, max(0.0, tv - T_INTRO) / DUR_ANIM)
            val i = busca(ta); val k = min(i + 1, n - 1)
            val w = if (k > i && act_[k] > act_[i] && sg[k] == sg[i]) (ta - act_[i]) / (act_[k] - act_[i]) else 0.0
            val cx = X[i] + (X[k] - X[i]) * w; val cy = Y[i] + (Y[k] - Y[i]) * w
            val vel = v[i] + (v[k] - v[i]) * w; val dd = dist[i] + (dist[k] - dist[i]) * w
            while (hecho < i) {
                val q = hecho + 1
                if (sg[q] == sg[hecho]) {
                    val p = trazo[bk((v[q] + v[hecho]) / 2)]
                    p.moveTo(X[hecho].toFloat(), Y[hecho].toFloat()); p.lineTo(X[q].toFloat(), Y[q].toFloat())
                }
                hecho = q
            }
            // cámara: sigue al cursor con suavizado y nunca lo deja fuera del 70% central
            val al = 1 - exp(-1.0 / (FPS * tau))
            var e = esc; val th: Double
            if (tv < T_INTRO) {                                           // paneo inicial: del área completa al cursor
                val bl = suave((tv - (T_INTRO - 0.9)) / 0.9)
                camX = acX + (cx - acX) * bl; camY = acY + (cy - acY) * bl
                e = (escAmplio * Math.pow((esc / escAmplio).toDouble(), bl)).toFloat()
                th = th0 + 360.0 * suave(tv / T_INTRO)
            } else if (tv < tFin) {                                       // recorrido: cámara pegada al cursor
                camX += (cx - camX) * al; camY += (cy - camY) * al
                val limX = W * 0.12 / esc; val limY = H * 0.12 / esc
                camX = min(max(camX, cx - limX), cx + limX); camY = min(max(camY, cy - limY), cy + limY)
                camFinX = camX; camFinY = camY
                th = th0 + 360.0 + 360.0 * (tv - T_INTRO) / DUR_ANIM
            } else {                                                      // paneo final: del cursor al área completa
                val bl = suave((tv - tFin) / 0.9)
                camX = camFinX + (acX - camFinX) * bl; camY = camFinY + (acY - camFinY) * bl
                e = (esc * Math.pow((escAmplio / esc).toDouble(), bl)).toFloat()
                th = th0 + 720.0 + 360.0 * suave((tv - tFin) / T_OUTRO)
            }
            val radioT = 6.0 * max(W, H) / e

            val c: Canvas = surf.lockHardwareCanvas()
            try {
                c.drawColor(Color.rgb(14, 42, 71))
                c.save()
                c.concat(persp)                                                   // plano -> pantalla (perspectiva)
                c.rotate((-th).toFloat()); c.scale(e, e); c.translate(-camX.toFloat(), -camY.toFloat())   // mundo -> plano
                for ((rf, bm) in fondo) c.drawBitmap(bm, null, rf, pBmp)
                val vx0 = floor((camX + OX - radioT) / 256).toInt(); val vx1 = floor((camX + OX + radioT) / 256).toInt()
                val vy0 = floor((camY + OY - radioT) / 256).toInt(); val vy1 = floor((camY + OY + radioT) / 256).toInt()
                for (ty in max(vy0, ty0)..min(vy1, ty1)) for (tx in max(vx0, tx0)..min(vx1, tx1)) {
                    val b = tiles[tx.toLong() * 100000L + ty] ?: continue
                    val l = ((tx - tx0) * 256).toFloat(); val tp = ((ty - ty0) * 256).toFloat()
                    c.drawBitmap(b, null, RectF(l, tp, l + 256.5f, tp + 256.5f), pBmp)
                }
                pSombra.strokeWidth = 14 * u / e
                for (p in trazo) c.drawPath(p, pSombra)
                pTrazo.strokeWidth = 8 * u / e
                for (b in 0..3) { pTrazo.color = SPD[b]; c.drawPath(trazo[b], pTrazo) }
                if (hecho < n && i < n) {          // último tramo hasta el cursor
                    pTrazo.color = SPD[bk(vel)]
                    c.drawLine(X[i].toFloat(), Y[i].toFloat(), cx.toFloat(), cy.toFloat(), pTrazo)
                }
                c.drawOval(RectF((cx - 16 * u / e).toFloat(), (cy - 16 * u / e).toFloat(), (cx + 16 * u / e).toFloat(), (cy + 16 * u / e).toFloat()), pSomb)
                c.restore()
                // cielo / bruma hacia el horizonte
                c.drawRect(0f, 0f, W.toFloat(), H * 0.34f, cielo)
                // cursor "parado" sobre el agua: posición en pantalla + palito + bola
                val rot = Math.toRadians(-th)
                val wx = (cx - camX) * e; val wy = (cy - camY) * e
                pt[0] = (wx * cos(rot) - wy * Math.sin(rot)).toFloat(); pt[1] = (wx * Math.sin(rot) + wy * cos(rot)).toFloat()
                // brújula: dirección del norte en pantalla (norte del mapa = -y, rotado y pasado por la perspectiva)
                val nb = floatArrayOf(pt[0], pt[1], pt[0] + (Math.sin(rot) * 200 * u).toFloat(), pt[1] - (cos(rot) * 200 * u).toFloat())
                persp.mapPoints(nb)
                val angN = atan2((nb[3] - nb[1]).toDouble(), (nb[2] - nb[0]).toDouble())
                persp.mapPoints(pt)
                val alto = 34 * u
                c.drawLine(pt[0], pt[1], pt[0], pt[1] - alto, pPalo)
                pPunto.color = Color.BLACK; c.drawCircle(pt[0], pt[1] - alto, 19 * u, pPunto)
                pPunto.color = Color.WHITE; c.drawCircle(pt[0], pt[1] - alto, 15 * u, pPunto)
                pPunto.color = SPD[bk(vel)]; c.drawCircle(pt[0], pt[1] - alto, 9 * u, pPunto)
                // datos: distancia recorrida (grande), velocidad máxima alcanzada hasta el momento (chica)
                // y, en el paneo final, la velocidad media en planeo
                if (tv >= T_INTRO - 0.3) {
                val mg = 40 * u; val L = Locale("es")
                val sd = if (dd < 1000) String.format(L, "%.0f", dd) else String.format(L, "%.2f", dd / 1000)
                val su = if (dd < 1000) "m" else "km"
                val vmx = vmaxHasta[i]
                val l1 = if (vmx > 0) "Vel. máx. " + String.format(L, "%.1f", vmx) + " kn" else null
                val fin = suave((tv - tFin) / 0.8)
                val l2 = if (tv >= tFin && vPlaneo > 0) (if (windsurf) "Vel. prom. " else "Vel. prom. planeo ") + String.format(L, "%.1f", vPlaneo) + " kn" else null
                var wb = pVel.measureText(sd) + 16 * u + pUni.measureText(su)
                if (l1 != null) wb = max(wb, pDist.measureText(l1))
                if (l2 != null) wb = max(wb, pDist.measureText(l2))
                wb += 2 * 32 * u
                val top = if (vertical) 120 * u else mg
                var h_ = 140f * u
                if (l1 != null) h_ += 62 * u
                if (l2 != null) h_ += (62 * u * fin).toFloat()
                c.drawRoundRect(RectF(mg, top, mg + wb, top + h_), 28 * u, 28 * u, pCaja)
                c.drawText(sd, mg + 32 * u, top + 104 * u, pVel)
                c.drawText(su, mg + 32 * u + pVel.measureText(sd) + 16 * u, top + 104 * u, pUni)
                if (l1 != null) c.drawText(l1, mg + 32 * u, top + 166 * u, pDist)
                if (l2 != null) {
                    pPlan.alpha = (255 * fin).toInt()
                    c.drawText(l2, mg + 32 * u, top + (if (l1 != null) 228 else 166) * u, pPlan)
                }
                }
                brujula(c, W - 40 * u - 78 * u, (if (vertical) 120 * u else 40 * u) + 78 * u, 78 * u, angN, u)
            } finally { surf.unlockCanvasAndPost(c) }
            drenar(false)
            if (f % 30 == 0) msg("Generando video… ${100 * f / total}%")
        }
        enc.signalEndOfInputStream()
        drenar(true)
        enc.stop(); enc.release(); surf.release()
        if (muxOn) mux.stop()
        mux.release()
        sinFoto = tiles.isEmpty() && fondo.isEmpty()
        for (b in tiles.values) b.recycle()
        for ((_, bm) in fondo) bm.recycle()

        // ---------- a Descargas/WingFoil
        msg("Guardando…")
        // el video nuevo reemplaza al anterior de esta sesión
        viejos = SessionInfo.deleteDownloads(act, dir, "video")
        val res = act.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, dir.name + "_video.mp4")
            put(MediaStore.Downloads.MIME_TYPE, "video/mp4")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/WingFoil")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = res.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: throw Exception("No se pudo guardar en Descargas.")
        res.openOutputStream(uri)?.use { os -> tmp.inputStream().use { it.copyTo(os) } }
        values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0); res.update(uri, values, null, null)
        SessionInfo.addDownload(dir, uri, "video")
        tmp.delete()
        return uri
    }
}
