package fr.coucou.android

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private val bg = Color(0xFF08090D)
private val surface = Color(0xFF151923)
private val accent = Color(0xFF7AA2FF)
private val mint = Color(0xFF4FD6A0)
private val muted = Color(0xFF929BAD)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme(colorScheme = darkColorScheme(primary=accent, background=bg, surface=surface)) { CoucouApp() } }
    }
}

@Composable
private fun CoucouApp() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("coucou", 0) }
    var host by remember { mutableStateOf(prefs.getString("host", "http://192.168.1.10:8765") ?: "") }
    var token by remember { mutableStateOf(prefs.getString("token", "") ?: "") }
    var setup by remember { mutableStateOf(true) }
    var expanded by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf(JSONObject()) }
    var error by remember { mutableStateOf("") }
    var chat by remember { mutableStateOf("") }
    var profile by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf(listOf("Coucou" to "Connecte-toi au pont Hermes de ton PC pour commencer.")) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val approvals = remember(status) { status.optJSONArray("approvals") ?: JSONArray() }
    val sessions = remember(status) { status.optJSONArray("sessions") ?: JSONArray() }
    val kanban = remember(status) { status.optJSONObject("kanban") ?: JSONObject() }
    val voiceLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (spoken.isNotBlank()) { chat = spoken; scope.launch { sendChat(spoken, host, token, profile) { messages = messages + ("Toi" to spoken) + ("Coucou" to it); chat = "" } } }
        }
    }
    suspend fun refresh() {
        try {
            val obj = api(host, token, "GET", "/api/status", null)
            status = obj; error = ""
        } catch (e: Exception) { error = e.message ?: "Connexion impossible" }
    }
    LaunchedEffect(host, token) { while (true) { if (!setup) refresh(); delay(2500) } }

    Box(Modifier.fillMaxSize().background(bg)) {
        Column(Modifier.fillMaxSize().padding(horizontal=16.dp)) {
            Spacer(Modifier.height(12.dp))
            // Island retracts to a small capsule when idle; tapping opens the panel.
            Row(Modifier.fillMaxWidth(), horizontalArrangement=Arrangement.Center) {
                Row(
                    Modifier.width(if (expanded) 360.dp else 112.dp).height(34.dp)
                        .background(Color(0xFF020204), RoundedCornerShape(24.dp))
                        .clickable { expanded = !expanded }.padding(horizontal=14.dp),
                    verticalAlignment=Alignment.CenterVertically, horizontalArrangement=Arrangement.Center
                ) {
                    Box(Modifier.size(7.dp).background(if (error.isEmpty()) mint else Color(0xFFFF6B7D), RoundedCornerShape(50)))
                    Spacer(Modifier.width(8.dp))
                    Text(if (expanded) "COUCOU  ·  HERMES" else "coucou", color=Color.White, fontSize=12.sp, fontWeight=FontWeight.SemiBold)
                    if (!expanded && (approvals.length()>0)) { Spacer(Modifier.width(7.dp)); Text("${approvals.length()}", color=accent, fontSize=11.sp) }
                }
            }
            Spacer(Modifier.height(20.dp))
            if (setup) {
                Text("Connexion au PC", color=Color.White, fontSize=25.sp, fontWeight=FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text("L’application Android se connecte au pont Coucou lancé sur le PC. Les agents et Hermes restent sur ton ordinateur.", color=muted)
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(host, { host=it }, label={Text("Adresse du PC, ex. http://192.168.1.20:8765")}, modifier=Modifier.fillMaxWidth(), singleLine=true)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(token, { token=it }, label={Text("Jeton d’accès")}, modifier=Modifier.fillMaxWidth(), singleLine=true)
                Spacer(Modifier.height(14.dp))
                Button(onClick={ prefs.edit().putString("host",host).putString("token",token).apply(); setup=false; scope.launch { refresh() } }, modifier=Modifier.fillMaxWidth()) { Text("Connecter") }
                Text("Conseil : utilise un réseau Wi-Fi de confiance et ne publie jamais le port sur Internet.", color=muted, fontSize=12.sp, modifier=Modifier.padding(top=12.dp))
            } else {
                Row(verticalAlignment=Alignment.CenterVertically, modifier=Modifier.fillMaxWidth()) {
                    Column(Modifier.weight(1f)) {
                        Text("Ton île", color=Color.White, fontSize=25.sp, fontWeight=FontWeight.Bold)
                        Text(if(error.isEmpty()) "Connecté au pont · actualisation automatique" else "Hors ligne : $error", color=if(error.isEmpty()) mint else Color(0xFFFF6B7D), fontSize=12.sp)
                    }
                    TextButton(onClick={ setup=true }) { Text("Réglages") }
                }
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp), modifier=Modifier.fillMaxWidth()) {
                    MiniTile("Agents", "${sessions.length()}", Modifier.weight(1f))
                    MiniTile("À valider", "${approvals.length()}", Modifier.weight(1f), if(approvals.length()>0) Color(0xFFFFB454) else accent)
                    MiniTile("Tâches", "${kanban.optInt("total",0)}", Modifier.weight(1f))
                }
                Spacer(Modifier.height(18.dp))
                Text("Demandes à valider", color=Color.White, fontSize=18.sp, fontWeight=FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                if(approvals.length()==0) Text("Aucune demande en attente.", color=muted, fontSize=13.sp)
                else LazyColumn(Modifier.heightIn(max=260.dp), verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    items((0 until approvals.length()).map { approvals.optJSONObject(it) ?: JSONObject() }) { ap ->
                        Column(Modifier.fillMaxWidth().background(surface, RoundedCornerShape(16.dp)).padding(13.dp)) {
                            Text("${ap.optString("agent")} · ${ap.optString("tool")}", color=Color.White, fontWeight=FontWeight.SemiBold)
                            Text(ap.optString("summary"), color=muted, fontSize=13.sp, modifier=Modifier.padding(vertical=7.dp))
                            Text("Risque ${ap.optInt("score")}/100  ${ap.optJSONArray("labels")?.join(", ") ?: ""}", color=if(ap.optInt("score")>=70) Color(0xFFFF6B7D) else Color(0xFFFFB454), fontSize=12.sp)
                            Row(horizontalArrangement=Arrangement.spacedBy(8.dp), modifier=Modifier.padding(top=10.dp)) {
                                Button(onClick={ scope.launch { act(host,token,"/api/approval/${ap.optString("id")}/allow"); refresh() } }, modifier=Modifier.weight(1f)) { Text("Autoriser") }
                                OutlinedButton(onClick={ scope.launch { act(host,token,"/api/approval/${ap.optString("id")}/deny"); refresh() } }, modifier=Modifier.weight(1f)) { Text("Refuser") }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(18.dp))
                Text("Discuter avec tes agents", color=Color.White, fontSize=18.sp, fontWeight=FontWeight.Bold)
                Spacer(Modifier.height(7.dp))
                OutlinedTextField(profile, {profile=it}, label={Text("Profil Hermes (optionnel)")}, placeholder={Text("ex. dev, recherche…")}, modifier=Modifier.fillMaxWidth(), singleLine=true)
                Spacer(Modifier.height(7.dp))
                LazyColumn(Modifier.weight(1f, fill=false).heightIn(min=110.dp, max=230.dp), verticalArrangement=Arrangement.spacedBy(7.dp)) {
                    items(messages.takeLast(30)) { (who, body) ->
                        Column(Modifier.fillMaxWidth().background(surface, RoundedCornerShape(13.dp)).padding(11.dp)) {
                            Text(who, color=accent, fontSize=11.sp, fontWeight=FontWeight.Bold)
                            Text(body, color=Color.White, fontSize=14.sp)
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment=Alignment.CenterVertically, horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                    OutlinedTextField(chat, {chat=it}, modifier=Modifier.weight(1f), placeholder={Text("Message à Hermes…")}, maxLines=3)
                    Button(enabled=!busy && chat.isNotBlank(), onClick={
                        val prompt=chat; busy=true; messages=messages+("Toi" to prompt)
                        scope.launch { sendChat(prompt,host,token,profile) { messages=messages+("Coucou" to it); chat="" }; busy=false }
                    }) { Text("Envoyer") }
                    IconButton(onClick={
                        val intent=Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
                            putExtra(RecognizerIntent.EXTRA_PROMPT, "Parle à Coucou")
                        }
                        try { voiceLauncher.launch(intent) } catch (_: Exception) { error="Reconnaissance vocale indisponible" }
                    }) { Text("🎙") }
                }
                Spacer(Modifier.height(10.dp))
                Text("Raccourcis smartphone", color=Color.White, fontWeight=FontWeight.Bold)
                Row(horizontalArrangement=Arrangement.spacedBy(7.dp), modifier=Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick={ scope.launch { act(host,token,"/api/shortcut/focus"); refresh() } }, modifier=Modifier.weight(1f)) { Text("Focus 25 min") }
                    OutlinedButton(onClick={ scope.launch { act(host,token,"/api/shortcut/bonjour"); refresh() } }, modifier=Modifier.weight(1f)) { Text("Brief vocal") }
                    OutlinedButton(onClick={ scope.launch { act(host,token,"/api/shortcut/calm"); refresh() } }, modifier=Modifier.weight(1f)) { Text("Respirer") }
                }
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}

@Composable
private fun MiniTile(label:String, value:String, modifier:Modifier=Modifier, color:Color=accent) {
    Column(modifier.background(surface, RoundedCornerShape(15.dp)).padding(12.dp)) {
        Text(label, color=muted, fontSize=12.sp); Text(value, color=color, fontSize=23.sp, fontWeight=FontWeight.Bold)
    }
}

private suspend fun sendChat(text:String, host:String, token:String, profile:String, result:(String)->Unit) {
    try {
        val body=JSONObject().put("text",text).put("profile",profile)
        val out=withContext(Dispatchers.IO) { api(host,token,"POST","/api/chat",body) }
        result(out.optString("reply","Message transmis à Hermes."))
    } catch(e:Exception) { result("Erreur : ${e.message ?: "connexion impossible"}") }
}
private suspend fun act(host:String, token:String, path:String) {
    withContext(Dispatchers.IO) { api(host,token,"POST",path,JSONObject()) }
}
private suspend fun api(host:String, token:String, method:String, path:String, body:JSONObject?):JSONObject = withContext(Dispatchers.IO) {
    val conn=URL(host.trimEnd('/')+path).openConnection() as HttpURLConnection
    conn.requestMethod=method; conn.connectTimeout=3500; conn.readTimeout=5000
    conn.setRequestProperty("Authorization","Bearer $token")
    conn.setRequestProperty("Content-Type","application/json; charset=utf-8")
    if(body!=null) { conn.doOutput=true; conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) } }
    try {
        val stream=if(conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val raw=stream.bufferedReader().use { it.readText() }
        if(conn.responseCode !in 200..299) throw IllegalStateException("HTTP ${conn.responseCode}: $raw")
        JSONObject(raw)
    } finally { conn.disconnect() }
}
