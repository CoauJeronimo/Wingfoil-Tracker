package uy.wingfoil.tracker

import android.content.Context
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

    /** Borra de Descargas los archivos de la sesión (de un tipo, o todos si tipo es null). */
    @Synchronized fun deleteDownloads(ctx: Context, dir: File, tipo: String? = null) {
        val j = load(dir); val arr = j.optJSONArray("descargas") ?: JSONArray(); val quedan = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            if (tipo == null || o.optString("tipo") == tipo) {
                try { ctx.contentResolver.delete(Uri.parse(o.getString("uri")), null, null) } catch (_: Exception) { }
            } else quedan.put(o)
        }
        j.put("descargas", quedan); save(dir, j)
        if (tipo == null) {
            // también lo que se haya guardado antes de llevar el registro y lleve el nombre de la sesión
            try {
                val sel = "${MediaStore.Downloads.DISPLAY_NAME} LIKE ? AND ${MediaStore.Downloads.RELATIVE_PATH} LIKE ?"
                ctx.contentResolver.delete(MediaStore.Downloads.EXTERNAL_CONTENT_URI, sel, arrayOf(dir.name + "%", "Download/WingFoil%"))
            } catch (_: Exception) { }
        }
    }
}
