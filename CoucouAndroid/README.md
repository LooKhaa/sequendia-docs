# Coucou Android 2.0 — compagnon mobile pour Hermes

Projet Android Studio (Kotlin + Jetpack Compose) et pont LAN pour `coucou-fedora`.

## 🚀 NOUVELLES FONCTIONNALITÉS VERSION 2.0

### 5 Fonctionnalités Mobiles Originales

1. **📝 Notes Rapides**
   - Créez des notes rapides avec horodatage
   - Accès rapide depuis l'interface principale
   - Synchronisation locale

2. **⏰ Rappels Intelligents**
   - Planifiez des rappels avec texte et heure
   - Notifications locales pour ne rien oublier
   - Gestion simple et intuitive

3. **📋 Synchronisation Presse-papiers**
   - Visualisez le dernier texte copié
   - Copiez des textes depuis l'application
   - Intégration transparente avec le système

4. **🔋 Moniteur de Batterie**
   - Affichage en temps réel du niveau de batterie
   - Indicateurs visuels (vert/orange/rouge)
   - Accès rapide aux paramètres d'économie d'énergie

5. **🧮 Calculatrice Rapide**
   - Calculatrice intégrée avec historique
   - Opérations mathématiques de base
   - Interface tactile optimisée

## Fonctionnalités existantes (améliorées)

- **Capsule rétractable** dans l'application et panneau mobile
- **État Hermes**, sessions d'agents, demandes d'approbation avec autoriser/refuser et score de risque
- **Chat** via les profils Hermes
- **Saisie vocale** ponctuelle avec la reconnaissance vocale Android
- **Raccourcis smartphone** : focus 25 minutes, brief vocal et respiration
- **Connexion au PC** par adresse IP + jeton

## 🎯 NOUVELLES CAPACITÉS

### Wake Word (Mot clé)
- **"Coucou"** : L'application peut écouter en arrière-plan et s'ouvrir automatiquement
- Nécessite l'activation dans les paramètres
- Utilise la reconnaissance vocale Android

### Encoche Flottante
- **Encoche au-dessus de toutes les applications**
- Apparaît quand il y a des notifications
- Se rétracte complètement quand inutilisée
- Déplaçable par glisser-déposer
- Nécessite la permission SYSTEM_ALERT_WINDOW

### Détection de Secousse
- **Secouez votre téléphone 3 fois** pour déclencher une action
- Technologie de détection de mouvement intégrée
- Personnalisable dans les paramètres

## 📱 Mise en route

### 1. Configuration du pont sur le PC

1. Sauvegardez le script PC original
2. `bridge/coucou-fedora-android.py` est une copie adaptée qui ajoute les opérations `resolve` et `ask_profile` au socket local
3. Vérifiez que Coucou démarre et que `coucou-fedora status` fonctionne
4. Lancez la copie adaptée au lieu du script d'origine pour exposer ces opérations locales

### 2. Création du jeton

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### 3. Lancement du pont

Dans le même terminal :
```bash
COUCOU_ANDROID_TOKEN='TON_JETON'
python3 bridge/coucou_bridge.py
```

Le port par défaut est 8765. Si le socket Coucou est ailleurs, définissez `COUCOU_SOCK`.

### 4. Autorisation du port

Autorisez ce port uniquement sur votre réseau Wi-Fi privé. **Ne publiez pas le service sur Internet.**

Le pont utilise HTTP sur le LAN; utilisez un VPN de confiance (par exemple Tailscale) sur un réseau non fiable.

### 5. Installation sur Android

1. Ouvrez ce dossier dans Android Studio
2. Synchronisez Gradle
3. Lancez sur un appareil Android
4. Saisissez `http://IP_DU_PC:8765` et le jeton

## ⚙️ Configuration des Permissions

### Permissions requises

- **INTERNET** : Pour la connexion au pont sur le PC
- **RECORD_AUDIO** : Pour la reconnaissance vocale
- **POST_NOTIFICATIONS** : Pour les notifications
- **FOREGROUND_SERVICE** : Pour le service en arrière-plan
- **SYSTEM_ALERT_WINDOW** : Pour l'encoche flottante (optionnelle)
- **VIBRATE** : Pour les retours haptiques
- **WAKE_LOCK** : Pour empêcher l'écran de s'éteindre

### Activation des fonctionnalités avancées

1. **Wake Word** :
   - Activez dans les paramètres de l'application
   - Nécessite la permission d'enregistrement audio
   - Consomme plus de batterie

2. **Encoche Flottante** :
   - Activez dans les paramètres de l'application
   - Nécessite la permission SYSTEM_ALERT_WINDOW
   - Allez dans Paramètres > Applications > Coucou > Permissions spéciales > Afficher par-dessus les autres applications

3. **Notifications** :
   - Activez dans les paramètres du téléphone
   - Permet de recevoir des alertes pour les demandes d'approbation

## 🎨 Interface Utilisateur

### Design
- **Thème sombre** par défaut
- **Couleurs personnalisées** : Bleu (#7AA2FF), Vert menthe (#4FD6A0), Orange (#FFB454), Rouge (#FF6B7D)
- **Animations fluides** pour une expérience utilisateur optimale
- **Adaptation automatique** à la taille de l'écran

### Navigation
- **Encoche supérieure** : Appuyez pour développer/réduire
- **Panneau principal** : Accès à toutes les fonctionnalités
- **Onglets** : Chat, Approbations, Outils mobile
- **Menu latéral** : Paramètres et informations

## 🔧 Dépannage

### Problèmes de connexion
- Vérifiez que le pont est en cours d'exécution sur le PC
- Assurez-vous que l'adresse IP est correcte
- Vérifiez que le jeton est valide
- Le port doit être accessible sur le réseau local

### Wake Word ne fonctionne pas
- Vérifiez que la permission microphone est accordée
- Assurez-vous que l'option est activée dans les paramètres
- Le service doit être en cours d'exécution
- La détection peut être affectée par le bruit ambiant

### Encoche flottante ne s'affiche pas
- Activez la permission SYSTEM_ALERT_WINDOW
- Redémarrez l'application
- Vérifiez que l'option est activée dans les paramètres

## 📊 Performances

### Optimisations
- **Rafraîchissement automatique** toutes les 2.5 secondes
- **Cache local** pour les données fréquentes
- **Désactivation intelligente** des fonctionnalités en arrière-plan
- **Gestion de la mémoire** optimisée

### Consommation batterie
- **Mode normal** : Faible consommation
- **Avec Wake Word** : Consommation modérée (écoute permanente)
- **Avec encoche flottante** : Consommation minimale

## 🔒 Sécurité

### Mesures de sécurité
- **Jeton d'authentification** obligatoire
- **Connexion chiffrée** (HTTP avec jeton, recommandé d'utiliser un VPN)
- **Pas de stockage** des données sensibles
- **Permissions minimales** requises

### Recommandations
- Utilisez toujours un **réseau Wi-Fi de confiance**
- **Ne partagez pas** votre jeton d'accès
- Utilisez un **VPN** sur les réseaux publics
- **Désactivez** les fonctionnalités non utilisées

## 📝 Historique des versions

### Version 2.0 (Actuelle)
- Ajout des 5 nouvelles fonctionnalités mobiles
- Support du Wake Word
- Encoche flottante améliorée
- Détection de secousse
- Interface utilisateur redessinée
- Meilleure gestion des permissions

### Version 1.0
- Version initiale
- Fonctionnalités de base : chat, approbations, raccourcis

## 🤝 Contribution

Les contributions sont les bienvenues !

### Comment contribuer
1. Forkez le dépôt
2. Créez une branche pour votre fonctionnalité (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commitez vos changements (`git commit -m 'Ajout de la nouvelle fonctionnalité'`)
4. Poussez vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrez une Pull Request

### Standards de code
- Suivez les conventions Kotlin
- Utilisez Jetpack Compose pour l'UI
- Documentez votre code
- Ajoutez des tests si possible

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.

## 🙏 Remerciements

- À la communauté Kotlin et Android
- À l'auteur original de Coucou
- À tous les contributeurs et testeurs
