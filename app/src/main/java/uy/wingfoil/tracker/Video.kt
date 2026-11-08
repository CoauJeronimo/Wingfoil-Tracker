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
 * recorrido sobre la foto satelital y gira despacio 90° a lo largo del video,
 * el trazo se pinta con los colores de velocidad y en pantalla solo van la velocidad del momento
 * y la distancia recorrida. 45 s, H.264, sin audio. Se arma en el teléfono con MediaCodec.
 */
object Video {
    private const val TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%d/%d/%d"
    private const val FPS = 30
    private const val DUR_ANIM = 43.0          // segundos de recorrido animado
    private const val DUR_TOTAL = 45.0         // + 2 s quieto al final
    private val SPD = intArrayOf(Color.WHITE, Color.rgb(0, 216, 74), Color.rgb(255, 212, 0), Color.rgb(255, 45, 45))
    private fun bk(v: Double) = if (v < 4) 0 else if (v < 7) 1 else if (v < 12) 2 else 3

    fun iniciar(act: Activity, dir: File) {
        val ops = arrayOf("Vertical 9:16 (historias de Instagram / WhatsApp)", "Horizontal 16:9")
        AlertDialog.Builder(act).setTitle("Video de la sesión (45 s)")
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
                    AlertDialog.Builder(act).setTitle("Video listo")
                        .setMessage("Quedó guardado en Descargas/WingFoil.")
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

    private fun merc(lat: Double, lon: Double, z: Int): DoubleArray {
        val nn = 256.0 * (1 shl z)
        val la = max(-85.0, min(85.0, lat)) * PI / 180
        return doubleArrayOf((lon + 180) / 360 * nn, (1 - ln(tan(la) + 1 / cos(la)) / PI) / 2 * nn)
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
        val lat = ArrayList<Double>(); val lon = ArrayList<Double>(); val t = ArrayList<Double>(); val v = ArrayList<Double>(); val sg = ArrayList<Int>()
        var segExtra = 0; var antesExcl = false
        for (i in 0 until a.length()) {
            val p = a.getJSONArray(i); val h = p.getString(5)
            if (excl.any { h >= it.first && h <= it.second }) { antesExcl = true; continue }
            if (antesExcl) { segExtra += 1000; antesExcl = false }
            t.add(p.getDouble(0)); lat.add(p.getDouble(1)); lon.add(p.getDouble(2)); v.add(p.getDouble(3)); sg.add(p.getInt(4) + segExtra)
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

        // ---------- encuadre: lo más cerca posible, pero que el cursor no cruce la pantalla en menos de ~1 s de video
        var latMin = lat.min(); var latMax = lat.max(); var lonMin = lon.min(); var lonMax = lon.max()
        val anchoM = (lonMax - lonMin) * kx; val altoM = (latMax - latMin) * ky
        val mPorSegVideo = dist[n - 1] / DUR_ANIM
        var vistaM = max(320.0, 1.3 * mPorSegVideo)                       // lado corto de la vista, en metros
        vistaM = min(vistaM, max(320.0, max(anchoM, altoM) * 1.1))
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
        val X = DoubleArray(n); val Y = DoubleArray(n)
        for (i in 0 until n) { val m = merc(lat[i], lon[i], z); X[i] = m[0]; Y[i] = m[1] }
        val mPorPx = 156543.03392 * cos(lat[0] * PI / 180) / (1 shl z)
        val esc = (corto / (vistaM / mPorPx)).toFloat()                 // px de pantalla por px de mundo

        // ---------- teselas satelitales
        msg("Descargando la foto satelital…")
        Tiles.cacheDir = File(act.filesDir, "tiles").apply { mkdirs() }; Tiles.reset()
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
            BitmapFactory.decodeByteArray(b, 0, b.size, opt)?.let { tiles[tx.toLong() * 100000L + ty] = it }
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
        val pDist = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 64 * u; typeface = Typeface.DEFAULT_BOLD }
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
        val radioT = 6.0 * max(W, H) / esc            // teselas a dibujar: hasta esta distancia de la cámara (px de mundo)
        val pt = FloatArray(2)
        var hecho = 0                                  // último índice ya agregado al trazo
        var camX = X[0]; var camY = Y[0]
        val tau = 0.5                                  // suavizado de la cámara (s de video)
        val total = (DUR_TOTAL * FPS).toInt()
        fun busca(ta: Double): Int { var lo = 0; var hi = n - 1; while (hi - lo > 1) { val m = (lo + hi) / 2; if (act_[m] <= ta) lo = m else hi = m }; return lo }
        for (f in 0 until total) {
            val tv = f.toDouble() / FPS
            val ta = totAct * min(1.0, tv / DUR_ANIM)
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
            if (f == 0) { camX = cx; camY = cy } else { camX += (cx - camX) * al; camY += (cy - camY) * al }
            val limX = W * 0.35 / esc; val limY = H * 0.35 / esc
            camX = min(max(camX, cx - limX), cx + limX); camY = min(max(camY, cy - limY), cy + limY)

            val c: Canvas = surf.lockHardwareCanvas()
            try {
                val th = th0 + 90.0 * tv / DUR_TOTAL
                c.drawColor(Color.rgb(14, 42, 71))
                c.save()
                c.concat(persp)                                                   // plano -> pantalla (perspectiva)
                c.rotate((-th).toFloat()); c.scale(esc, esc); c.translate(-camX.toFloat(), -camY.toFloat())   // mundo -> plano
                val vx0 = floor((camX + OX - radioT) / 256).toInt(); val vx1 = floor((camX + OX + radioT) / 256).toInt()
                val vy0 = floor((camY + OY - radioT) / 256).toInt(); val vy1 = floor((camY + OY + radioT) / 256).toInt()
                for (ty in max(vy0, ty0)..min(vy1, ty1)) for (tx in max(vx0, tx0)..min(vx1, tx1)) {
                    val b = tiles[tx.toLong() * 100000L + ty] ?: continue
                    val l = ((tx - tx0) * 256).toFloat(); val tp = ((ty - ty0) * 256).toFloat()
                    c.drawBitmap(b, null, RectF(l, tp, l + 256.5f, tp + 256.5f), pBmp)
                }
                pSombra.strokeWidth = 14 * u / esc
                for (p in trazo) c.drawPath(p, pSombra)
                pTrazo.strokeWidth = 8 * u / esc
                for (b in 0..3) { pTrazo.color = SPD[b]; c.drawPath(trazo[b], pTrazo) }
                if (hecho < n && i < n) {          // último tramo hasta el cursor
                    pTrazo.color = SPD[bk(vel)]
                    c.drawLine(X[i].toFloat(), Y[i].toFloat(), cx.toFloat(), cy.toFloat(), pTrazo)
                }
                c.drawOval(RectF((cx - 16 * u / esc).toFloat(), (cy - 16 * u / esc).toFloat(), (cx + 16 * u / esc).toFloat(), (cy + 16 * u / esc).toFloat()), pSomb)
                c.restore()
                // cielo / bruma hacia el horizonte
                c.drawRect(0f, 0f, W.toFloat(), H * 0.34f, cielo)
                // cursor "parado" sobre el agua: posición en pantalla + palito + bola
                val rot = Math.toRadians(-th)
                val wx = (cx - camX) * esc; val wy = (cy - camY) * esc
                pt[0] = (wx * cos(rot) - wy * Math.sin(rot)).toFloat(); pt[1] = (wx * Math.sin(rot) + wy * cos(rot)).toFloat()
                persp.mapPoints(pt)
                val alto = 34 * u
                c.drawLine(pt[0], pt[1], pt[0], pt[1] - alto, pPalo)
                pPunto.color = Color.BLACK; c.drawCircle(pt[0], pt[1] - alto, 19 * u, pPunto)
                pPunto.color = Color.WHITE; c.drawCircle(pt[0], pt[1] - alto, 15 * u, pPunto)
                pPunto.color = SPD[bk(vel)]; c.drawCircle(pt[0], pt[1] - alto, 9 * u, pPunto)
                // datos: velocidad del momento y distancia recorrida
                val mg = 40 * u
                val sv = String.format(Locale("es"), "%.1f", vel); val sd = if (dd < 1000) String.format(Locale("es"), "%.0f m", dd) else String.format(Locale("es"), "%.2f km", dd / 1000)
                val wv = pVel.measureText(sv) + 16 * u + pUni.measureText("kn")
                val wb = max(wv, pDist.measureText(sd)) + 2 * 32 * u
                val top = if (vertical) 120 * u else mg
                c.drawRoundRect(RectF(mg, top, mg + wb, top + 210 * u), 28 * u, 28 * u, pCaja)
                c.drawText(sv, mg + 32 * u, top + 104 * u, pVel)
                c.drawText("kn", mg + 32 * u + pVel.measureText(sv) + 16 * u, top + 104 * u, pUni)
                c.drawText(sd, mg + 32 * u, top + 180 * u, pDist)
            } finally { surf.unlockCanvasAndPost(c) }
            drenar(false)
            if (f % 30 == 0) msg("Generando video… ${100 * f / total}%")
        }
        enc.signalEndOfInputStream()
        drenar(true)
        enc.stop(); enc.release(); surf.release()
        if (muxOn) mux.stop()
        mux.release()
        for (b in tiles.values) b.recycle()

        // ---------- a Descargas/WingFoil
        msg("Guardando…")
        SessionInfo.deleteDownloads(act, dir, "video")
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
