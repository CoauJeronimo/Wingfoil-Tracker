package uy.wingfoil.tracker

import android.app.Activity
import android.content.Context
import android.os.Build
import android.net.Uri
import android.provider.MediaStore
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Datos propios de cada sesión (info.json dentro de su carpeta): nombre, lugar, intensidad del viento,
 * comentario y los archivos que la app guardó en Descargas (para borrarlos junto con la sesión).
 */
object SessionInfo {
    private fun file(dir: File) = File(dir, "info.json")

    fun load(dir: File): JSONObject = try {
        file(dir).takeIf { it.exists() }?.readText()?.let { JSONObject(it) } ?: JSONObject()
    } catch (_: Exception) { JSONObject() }

    @Synchronized fun save(dir: File, j: JSONObject) { try { file(dir).writeText(j.toString()) } catch (_: Exception) { } }

    fun get(dir: File, k: String): String = load(dir).optString(k, "")

    fun set(dir: File, vararg kv: Pair<String, String>) {
        val j = load(dir); for ((k, v) in kv) j.put(k, v.trim()); save(dir, j)
    }

    /** Registra un archivo guardado en Descargas, con su tipo (zip, gpx, analisis). */
    @Synchronized fun addDownload(dir: File, uri: Uri, tipo: String) {
        val j = load(dir); val arr = j.optJSONArray("descargas") ?: JSONArray()
        arr.put(JSONObject().put("uri", uri.toString()).put("tipo", tipo)); j.put("descargas", arr); save(dir, j)
    }

    /**
     * Borra de Descargas los archivos de la sesión (de un tipo, o todos si tipo es null).
     * Devuelve los que Android no dejó borrar sin preguntar (p. ej. guardados por una instalación anterior de la app):
     * esos se pueden borrar con [pedirBorrado], que le pide permiso al usuario.
     */
    @Synchronized fun deleteDownloads(ctx: Context, dir: File, tipo: String? = null): List<Uri> {
        val j = load(dir); val arr = j.optJSONArray("descargas") ?: JSONArray(); val quedan = JSONArray()
        val trabados = ArrayList<Uri>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (tipo == null || o.optString("tipo") == tipo) {
                val u = Uri.parse(o.getString("uri"))
                try { ctx.contentResolver.delete(u, null, null) }
                catch (_: SecurityException) { if (existe(ctx, u)) trabados.add(u) }
                catch (_: Exception) { }
            } else quedan.put(o)
        }
        j.put("descargas", quedan); save(dir, j)
        // también lo que haya quedado con el nombre de la sesión (copias "(1)", "(2)"… o sin registrar)
        val patron = when (tipo) { null -> dir.name + "%"; "video" -> dir.name + "_video%"; else -> null }
        if (patron != null) try {
            val sel = "${MediaStore.Downloads.DISPLAY_NAME} LIKE ? AND ${MediaStore.Downloads.RELATIVE_PATH} LIKE ?"
            ctx.contentResolver.delete(MediaStore.Downloads.EXTERNAL_CONTENT_URI, sel, arrayOf(patron, "Download/WingFoil%"))
        } catch (_: Exception) { }
        return trabados
    }

    private fun existe(ctx: Context, u: Uri): Boolean = try {
        ctx.contentResolver.query(u, arrayOf(MediaStore.MediaColumns._ID), null, null, null)?.use { it.count > 0 } ?: false
    } catch (_: SecurityException) { true } catch (_: Exception) { false }

    /** Pide al usuario permiso para borrar archivos que la app no puede borrar sola (Android 11 o superior). */
    fun pedirBorrado(act: Activity, uris: List<Uri>) {
        if (uris.isEmpty() || Build.VERSION.SDK_INT < 30) return
        try {
            val pi = MediaStore.createDeleteRequest(act.contentResolver, uris)
            act.startIntentSenderForResult(pi.intentSender, 4711, null, 0, 0, 0)
        } catch (_: Exception) { }
    }
}
