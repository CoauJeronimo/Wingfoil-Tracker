package uy.wingfoil.tracker

import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.graphics.Color
import android.graphics.Typeface
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject

/**
 * Checklist de equipamiento: lista editable (agregar, renombrar, mover, borrar) que se guarda en el teléfono.
 * Tocar un ítem lo tilda; mantenerlo apretado abre las opciones (editar, subir, bajar, borrar).
 */
object Checklist {
    private const val PREF = "checklist"
    private val BG = Color.rgb(6, 20, 38); private val CARD = Color.rgb(13, 35, 64)
    private val VERDE = Color.rgb(46, 229, 157); private val MUT = Color.rgb(143, 169, 199)

    private val DEFAULT = listOf(
        "Wing (sin roturas, válvulas cerradas)", "Inflador", "Tabla", "Foil: mástil, fuselaje, ala delantera y estabilizador",
        "Tornillos y llave del foil", "Leash de la wing", "Leash de la tabla", "Casco", "Chaleco / protección de impacto",
        "Traje, botitas y guantes", "Teléfono cargado, en la funda estanca", "App grabando (GPS OK)",
        "Agua y protector solar", "Revisar viento y pronóstico")

    private fun cargar(act: Activity): MutableList<JSONObject> {
        val p = act.getSharedPreferences("wf", Activity.MODE_PRIVATE)
        val s = p.getString(PREF, null)
        val out = ArrayList<JSONObject>()
        if (s == null) DEFAULT.forEach { out.add(JSONObject().put("t", it).put("ok", false)) }
        else try { val a = JSONArray(s); for (i in 0 until a.length()) out.add(a.getJSONObject(i)) } catch (_: Exception) { }
        return out
    }

    private fun guardar(act: Activity, items: List<JSONObject>) {
        val a = JSONArray(); items.forEach { a.put(it) }
        act.getSharedPreferences("wf", Activity.MODE_PRIVATE).edit().putString(PREF, a.toString()).apply()
    }

    fun mostrar(act: Activity) {
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val items = cargar(act)
        val dlg = Dialog(act, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(BG); setPadding(dp(16), dp(18), dp(16), dp(12)) }
        root.addView(LinearLayout(act).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            addView(ImageView(act).apply { setImageResource(R.drawable.ic_checklist); layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply { rightMargin = dp(10) } })
            addView(TextView(act).apply { text = "Checklist de Equipamiento"; textSize = 21f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD })
        })
        val estado = TextView(act).apply { textSize = 14f; setTextColor(MUT); setPadding(0, dp(6), 0, dp(4)) }
        root.addView(estado)
        root.addView(TextView(act).apply {
            text = "Tocá un ítem para tildarlo. Mantenelo apretado para editarlo, moverlo o borrarlo."
            textSize = 12.5f; setTextColor(MUT); setPadding(0, 0, 0, dp(8))
        })
        val lista = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        root.addView(ScrollView(act).apply { addView(lista); layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f) })

        fun pedirTexto(titulo: String, ini: String, ok: (String) -> Unit) {
            val e = EditText(act).apply { setText(ini); setSelection(ini.length); inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
            AlertDialog.Builder(act).setTitle(titulo).setView(LinearLayout(act).apply { setPadding(dp(20), dp(8), dp(20), 0); addView(e, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT)) })
                .setPositiveButton("Guardar") { _, _ -> val t = e.text.toString().trim(); if (t.isNotEmpty()) ok(t) }
                .setNegativeButton("Cancelar", null).show()
        }

        lateinit var pintar: () -> Unit
        pintar = {
            lista.removeAllViews()
            val listos = items.count { it.optBoolean("ok") }
            estado.text = if (items.isEmpty()) "La lista está vacía: agregá lo que llevás." else
                "$listos de ${items.size} listos" + if (listos == items.size) "  ✔ ¡Todo listo!" else ""
            estado.setTextColor(if (items.isNotEmpty() && listos == items.size) VERDE else MUT)
            items.forEachIndexed { i, it ->
                val cb = CheckBox(act).apply {
                    text = it.optString("t"); isChecked = it.optBoolean("ok"); textSize = 17f
                    setTextColor(if (isChecked) MUT else Color.WHITE)
                    buttonTintList = android.content.res.ColorStateList.valueOf(VERDE)
                    setPadding(dp(6), dp(12), dp(6), dp(12)); setBackgroundColor(CARD)
                    layoutParams = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(6) }
                    setOnCheckedChangeListener { _, c -> it.put("ok", c); guardar(act, items); pintar() }
                    setOnLongClickListener { _ ->
                        val ops = arrayOf("Editar", "Subir", "Bajar", "Borrar")
                        AlertDialog.Builder(act).setTitle(it.optString("t")).setItems(ops) { _, w ->
                            when (w) {
                                0 -> pedirTexto("Editar ítem", it.optString("t")) { t -> it.put("t", t); guardar(act, items); pintar() }
                                1 -> if (i > 0) { items.add(i - 1, items.removeAt(i)); guardar(act, items); pintar() }
                                2 -> if (i < items.size - 1) { items.add(i + 1, items.removeAt(i)); guardar(act, items); pintar() }
                                3 -> AlertDialog.Builder(act).setMessage("¿Borrar \"${it.optString("t")}\"?")
                                    .setPositiveButton("Borrar") { _, _ -> items.removeAt(i); guardar(act, items); pintar() }
                                    .setNegativeButton("Cancelar", null).show()
                            }
                        }.show(); true
                    }
                }
                lista.addView(cb)
            }
        }
        pintar()

        fun boton(t: String, bg: Int, fg: Int, peso: Float, f: () -> Unit) = Button(act).apply {
            text = t; isAllCaps = false; textSize = 15f; typeface = Typeface.DEFAULT_BOLD; setTextColor(fg); setBackgroundColor(bg)
            layoutParams = LinearLayout.LayoutParams(0, WRAP_CONTENT, peso).apply { setMargins(dp(3), dp(10), dp(3), 0) }
            setOnClickListener { f() }
        }
        root.addView(LinearLayout(act).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(boton("+ Agregar", VERDE, Color.BLACK, 1f) { pedirTexto("Nuevo ítem", "") { t -> items.add(JSONObject().put("t", t).put("ok", false)); guardar(act, items); pintar() } })
            addView(boton("Destildar todo", CARD, Color.WHITE, 1f) { items.forEach { it.put("ok", false) }; guardar(act, items); pintar() })
        })
        root.addView(LinearLayout(act).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(boton("Lista de ejemplo", CARD, MUT, 1f) {
                AlertDialog.Builder(act).setMessage("¿Reemplazar tu lista por la lista de ejemplo?")
                    .setPositiveButton("Reemplazar") { _, _ -> items.clear(); DEFAULT.forEach { items.add(JSONObject().put("t", it).put("ok", false)) }; guardar(act, items); pintar() }
                    .setNegativeButton("Cancelar", null).show()
            })
            addView(boton("Cerrar", CARD, Color.WHITE, 1f) { dlg.dismiss() })
        })
        dlg.setContentView(root)
        dlg.show()
    }
}
