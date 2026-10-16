# Coucou Android — compagnon mobile pour Hermes

Projet Android Studio (Kotlin + Jetpack Compose) et pont LAN pour `coucou-fedora`.

## Fonctionnalités
- Capsule rétractable dans l'application et panneau mobile.
- État Hermes, sessions d'agents, demandes d'approbation avec autoriser/refuser et score de risque.
- Chat via les profils Hermes.
- Saisie vocale ponctuelle avec la reconnaissance vocale Android.
- Raccourcis smartphone : focus 25 minutes, brief vocal et respiration.
- Connexion au PC par adresse IP + jeton.

## Mise en route
1. Sauvegarde le script PC original. `bridge/coucou-fedora-android.py` est une copie adaptée qui ajoute les opérations `resolve` et `ask_profile` au socket local.
2. Vérifie que Coucou démarre et que `coucou-fedora status` fonctionne. Lance la copie adaptée au lieu du script d'origine pour exposer ces opérations locales.
3. Crée un jeton : `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
4. Dans le même terminal, définis `COUCOU_ANDROID_TOKEN='TON_JETON'`, puis lance `python3 bridge/coucou_bridge.py`. Le port par défaut est 8765. Si le socket Coucou est ailleurs, définis `COUCOU_SOCK`.
5. Autorise ce port uniquement sur ton réseau Wi-Fi privé. Ne publie pas le service sur Internet. Le pont utilise HTTP sur le LAN; utilise un VPN de confiance (par exemple Tailscale) sur un réseau non fiable.
6. Ouvre ce dossier dans Android Studio, synchronise Gradle, lance sur un appareil Android et saisis `http://IP_DU_PC:8765` et le jeton.

## Cinq fonctions mobiles proposées / incluses
1. Validation des actions Hermes depuis le téléphone avec score de risque.
2. Chat ciblé sur un profil Hermes.
3. Saisie vocale mains libres à la demande.
4. Focus mobile en un toucher.
5. Brief du matin et respiration guidée déclenchés à distance.

## Limites actuelles
- La capsule se rétracte dans l'interface de l'app; une encoche globale au-dessus de toutes les apps exige une permission de superposition et une adaptation spécifique à Android.
- Le bouton micro lance la reconnaissance vocale à la demande. Le wakeword permanent « Coucou » n'est pas implémenté : il exige un moteur wake-word embarqué et un service au premier plan avec notification persistante et permissions explicites. Le micro n'écoute donc pas en permanence.
- Ollama/Qwen local n'est pas utilisé sur le téléphone.
- Le dépôt contient le code source, pas un APK compilé. Compilation avec Android Studio et SDK Android 35.
