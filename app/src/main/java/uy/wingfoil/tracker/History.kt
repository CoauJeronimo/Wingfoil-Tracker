package uy.wingfoil.tracker

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import java.util.Locale

/** Histórico: junta los resultados de las sesiones analizadas (analisis/resultados.json). */
object History {

    private class Ses(val r: JSONObject) {
        val T = r.optJSONObject("por_tipo")?.optJSONObject("Trasluchada") ?: JSONObject()
        val V = r.optJSONObject("por_tipo")?.optJSONObject("Virada") ?: JSONObject()
        val acc = r.optBoolean("acc", false)
        val saltos = r.optJSONArray("saltos")
        val sc: Int get() = if (saltos == null) 0 else (0 until saltos.length()).count { saltos.getJSONObject(it).optString("resultado") == "Completo" }
        val sf: Int get() = (saltos?.length() ?: 0) - sc
        val orden: String get() {
            val f = r.optString("fecha").split("-")
            return if (f.size == 3) f[2] + f[1] + f[0] + r.optString("hora_inicio") else r.optString("fecha")
        }
    }

    private fun leer(a: Activity): List<Ses> =
        (TrackService.sessionsRoot(a).listFiles() ?: emptyArray()).mapNotNull { d ->
            val f = File(d, "analisis/resultados.json")
            if (!f.exists()) null else try { Ses(JSONObject(f.readText())) } catch (_: Exception) { null }
        }.sortedByDescending { it.orden }

    private fun d(o: JSONObject, k: String): Double? = if (o.has(k) && !o.isNull(k)) o.optDouble(k).takeIf { !it.isNaN() } else null
    private fun f1(x: Double?, suf: String = "") = if (x == null) "s/d" else String.format(Locale("es"), "%.1f", x) + suf
    private fun pct(x: Double?, signo: Boolean = false) =
        if (x == null) "s/d" else String.format(Locale("es"), if (signo) "%+.1f%%" else "%.1f%%", x * 100)

    /** Promedio ponderado por cantidad de maniobras COMPLETAS (las velocidades se calculan solo con completas). */
    private fun pond(L: List<Ses>, tipo: (Ses) -> JSONObject, k: String): Double? {
        var s = 0.0; var w = 0
        for (x in L) {
            val o = tipo(x); val v = d(o, k) ?: continue
            val n = o.optInt("completas"); s += v * n; w += n
        }
        return if (w > 0) s / w else null
    }

    fun mostrar(a: Activity) {
        val L = leer(a)
        val dens = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * dens).toInt()
        val box = LinearLayout(a).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(8)) }
        fun tv(t: String, size: Float, color: Int = Color.WHITE, bold: Boolean = false) = TextView(a).apply {
            text = t; textSize = size; setTextColor(color); if (bold) typeface = Typeface.DEFAULT_BOLD
        }
        if (L.isEmpty()) {
            box.addView(tv("Todavía no hay sesiones analizadas.\nAnalizá una sesión (📊 Analizar) y va a aparecer acá.", 15f))
            AlertDialog.Builder(a).setTitle("📈 Histórico").setView(box).setPositiveButton("Cerrar", null).show()
            return
        }
        // ---- totales
        val min = L.sumOf { d(it.r, "tiempo_min") ?: 0.0 }
        val plan = L.sumOf { d(it.r, "planeo_min") ?: 0.0 }
        val tc = L.sumOf { it.T.optInt("completas") }; val tf = L.sumOf { it.T.optInt("fallidas") }
        val vc = L.sumOf { it.V.optInt("completas") }; val vf = L.sumOf { it.V.optInt("fallidas") }
        val conAcc = L.filter { it.acc }
        val sc = conAcc.sumOf { it.sc }; val sf = conAcc.sumOf { it.sf }
        val fT = { s: Ses -> s.T }; val fV = { s: Ses -> s.V }
        val tot = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(13, 35, 64)); setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        tot.addView(tv("TOTAL · ${L.size} sesion${if (L.size > 1) "es" else ""}", 13f, Color.rgb(143, 169, 199), true))
        tot.addView(tv(
            "Tiempo ${f1(min / 60, " h")} · Planeo ${pct(if (min > 0) plan / min else null)}\n" +
            "Trasluchadas $tc / $tf (éxito ${pct(if (tc + tf > 0) tc.toDouble() / (tc + tf) else null)})\n" +
            "   completas: ${f1(pond(L, fT, "v_in"), " kn")} → ${f1(pond(L, fT, "v_out"), " kn")} (${pct(pond(L, fT, "variacion"), true)})\n" +
            "Viradas $vc / $vf (éxito ${pct(if (vc + vf > 0) vc.toDouble() / (vc + vf) else null)})\n" +
            "   completas: ${f1(pond(L, fV, "v_in"), " kn")} → ${f1(pond(L, fV, "v_out"), " kn")} (${pct(pond(L, fV, "variacion"), true)})\n" +
            "Saltos $sc / $sf" + if (conAcc.size < L.size) "  (sin acelerómetro en ${L.size - conAcc.size})" else "",
            14f))
        box.addView(tot)
        box.addView(tv("Cantidades: completas / fallidas. Velocidades (entrada → salida) y variación: solo maniobras completas.", 11f, Color.rgb(143, 169, 199)).apply { setPadding(0, dp(4), 0, dp(8)) })
        // ---- una tarjeta por sesión
        for (s in L) {
            val r = s.r
            val c = LinearLayout(a).apply {
                orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(9, 28, 52)); setPadding(dp(14), dp(10), dp(14), dp(10))
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) }
            }
            val nom = r.optString("nombre", ""); val lug = r.optString("lugar", "")
            val vkn = d(r, "viento_kn")
            c.addView(tv(if (nom.isNotEmpty()) nom else "${r.optString("fecha")} · ${r.optString("hora_inicio").take(5)}", 15f, Color.WHITE, true))
            c.addView(tv(listOfNotNull(if (nom.isNotEmpty()) "${r.optString("fecha")} ${r.optString("hora_inicio").take(5)}" else null,
                lug.ifEmpty { null }, "viento ${r.optDouble("viento", 0.0).toInt()}°" + (if (vkn != null) " ${f1(vkn, " kn")}" else ""),
                f1(d(r, "distancia_km"), " km")).joinToString(" · "), 12.5f, Color.rgb(143, 169, 199)))
            c.addView(tv(
                "Duración ${f1(d(r, "tiempo_min"), " min")} · Planeo ${pct(d(r, "planeo_pct"))}\n" +
                "Trasluchadas ${s.T.optInt("completas")} / ${s.T.optInt("fallidas")} · ${f1(d(s.T, "v_in"))} → ${f1(d(s.T, "v_out"), " kn")} (${pct(d(s.T, "variacion"), true)})\n" +
                "Viradas ${s.V.optInt("completas")} / ${s.V.optInt("fallidas")} · ${f1(d(s.V, "v_in"))} → ${f1(d(s.V, "v_out"), " kn")} (${pct(d(s.V, "variacion"), true)})\n" +
                "Saltos " + if (s.acc) "${s.sc} / ${s.sf}" else "s/d", 13.5f, Color.rgb(200, 215, 230)))
            val com = r.optString("comentario", "")
            if (com.isNotEmpty()) c.addView(tv("“$com”", 13f, Color.rgb(255, 212, 0)).apply { setTypeface(typeface, Typeface.ITALIC) })
            box.addView(c)
        }
        AlertDialog.Builder(a)
            .setTitle("📈 Histórico")
            .setView(ScrollView(a).apply { addView(box) })
            .setPositiveButton("Cerrar", null)
            .setNeutralButton("Exportar Excel") { _, _ -> exportar(a) }
            .show()
    }

    private fun exportar(a: Activity) {
        val wait = AlertDialog.Builder(a).setMessage("Armando el Excel…").setCancelable(false).show()
        Thread {
            var msg: String? = null; var uri: android.net.Uri? = null
            try {
                Analysis.ensurePython(a)
                val out = File(a.cacheDir, "historico_wingfoil.xlsx")
                val j = JSONObject(Python.getInstance().getModule("historico")
                    .callAttr("exportar", TrackService.sessionsRoot(a).absolutePath, out.absolutePath).toString())
                if (!j.optBoolean("ok")) msg = j.optString("error")
                else uri = Analysis.saveToDownloads(a, out, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Historico")
            } catch (e: Throwable) { msg = e.toString() }
            a.runOnUiThread {
                wait.dismiss()
                if (uri == null) { Toast.makeText(a, msg ?: "No se pudo crear el Excel", Toast.LENGTH_LONG).show(); return@runOnUiThread }
                Toast.makeText(a, "Guardado en Descargas/WingFoil/Historico", Toast.LENGTH_LONG).show()
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                a.startActivity(Intent.createChooser(send, "Compartir histórico"))
            }
        }.start()
    }
}
