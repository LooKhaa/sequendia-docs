# Sequendia — Spécification de génération des fiches
*Version 1 — 20/09/2026. Ce document est la source de vérité pour toute génération de séquence. Une fiche est acceptée uniquement si elle respecte chaque règle. Objectif : rendu final direct, zéro retouche manuelle.*

---

## Règles globales (toutes les fiches)

1. **Aucune syntaxe markdown dans le document final.** Les `**`, `###`, `>`, `---`, `|` de tableaux markdown sont interdits dans le .docx : ils doivent être convertis en vraie mise en forme Word (gras réel, styles de titre, citations indentées, vrais tableaux Word).
2. **Accords et accents complets partout**, y compris dans les versions DYS (la population dyslexique a plus besoin des accents que les autres, pas moins). Interdits : « etait », « restee », « adapte ».
3. **Pas d'emoji comme puce ou titre.** À l'impression N&B, ils ressortent en carrés. Utiliser des puces typographiques (•, —, →) et des en-têtes de style Word.
4. **Fond de page standard Sequendia** : en-tête `Niveau – Discipline – Titre séquence – Type de fiche`, pied de page avec numéro de fiche (ex. « Séance 2/5 – Fiche élève »). Un seul gabarit, identique d'une séquence à l'autre.
5. **Corrections automatiques obligatoires avant export** : passe de relecture par le générateur (orthographe, cohérence des numéros d'exercices, absence de doublons/contradictions entre sections).
6. **Structure de dossiers imposée** : `Niveau_Sequences/<Titre>/Seance-N/Seance-N_Eleve.docx | Seance-N_Prof.docx | Seance-N_DYS.docx`.

---

## Fiche élève

- En-tête avec nom/date ; objectif de la séquence rappelé en une phrase.
- Texte support original (inventé de préférence : zéro risque de droits d'auteur) dans un encadré visuel distinct, avec titre.
- Trace écrite à compléter (trous) : les trous ne doivent jamais supprimer un mot porteur de sens de la consigne ; une clé de passage est donnée dans le contexte proche.
- Exercices numérotés en continu (1 à 10), répartis en 3 niveaux de difficulté affichés :
  - Niveau 1 — Repérage (3 exercices)
  - Niveau 2 — Analyse et classement (3 exercices)
  - Niveau 3 — Production (4 exercices, dont 1 de rédaction avec critère de réussite explicite)
- Une ligne par item de consigne — jamais deux exercices fusionnés sur la même ligne.
- Distracteurs pertinents dans au moins 1 exercice (ex. un mot qui ressemble à une expansion mais n'en est pas une).
- Section « Pour aller plus loin » facultative, max 3 lignes.

## Fiche prof

- **Déroulé minuté obligatoire en tête de fiche**, sous forme de tableau Word : colonnes `Durée | Phase | Activité (enseignant) | Activité (élèves)`. Somme des durées = durée de la séance annoncée (55 min). Ne jamais écraser cette section par un autre tableau.
- Objectifs formulés en comportement observable avec critère de réussite chiffré (ex. « au moins 8/10 »), pas en « comprendre ».
- Prérequis listés (ce qui est supposé vu en amont).
- Contenu disciplinaire : définitions, tableau des notions, exemples — le prof ne doit pas avoir besoin d'ouvrir la fiche élève pour corriger.
- **Corrigé complet de TOUS les exercices de la fiche élève**, y compris les réponses « libres » (donner 2-3 réponses exemplaires). Corrigés en toutes lettres (pas d'abréviations type « adj. epith. »). Vérifier chaque corrigé phrase par phrase (pas d'erreur de type « habitait la » pour « là »).
- Encadré « Difficultés prévisibles et remédiations » (2-4 points).

## Fiche DYS (version adaptée) — exigences fortes

La version DYS est **une fiche complète et autonome**, pas une notice :
- **Mêmes objectifs et mêmes exercices que la fiche élève**, sauf réduction explicite (consigne globale en tête : « Exercices 1-5 »). Jamais uniquement des consignes administratives.
- Mise en page : police Arial 14 minimum (ou OpenDyslexic en variante), interligne 1,5, texte aligné à gauche (jamais justifié), mots non coupés, fond blanc, pas d'images décoratives.
- Consignes reformulées en phrases courtes (< 15 mots), une instruction par ligne, avec numérotation très visible.
- Texte support : version simplifiée du même texte (phrases plus courtes, vocabulaire conservé), **avec accents**.
- Espaces de réponse agrandis (lignes de réponse à double interligne).
- Bandeau d'aide en tête : ce qui est à disposition de l'élève (fiche mémo, tableau).
- Trace écrite simplifiée complète (avec les trous déjà plus rares), pas une phrase inachevée.

---

## Contrôle qualité final (auto-vérification du générateur avant livraison)

Le générateur doit cocher lui-même ces 8 points et signaler tout échec :
1. Aucun caractère markdown résiduel dans aucun des 3 fichiers.
2. Tous les accents corrects (recherche des patterns typiques : mots finissant en "-ait/-ee/-e" sans accent dans le DYS).
3. Le tableau « déroulé minuté » existe et la somme des durées = durée annoncée.
4. Chaque exercice de la fiche élève a son corrigé dans la fiche prof.
5. Les 3 fiches de la séance portent le même titre, le même numéro de séance et la même séquence.
6. Aucune section dupliquée ou écrasée (le contenu de chaque titre est spécifique à ce titre).
7. Nommage de fichiers conforme.
8. Une ligne = un item (recherche de numéros consécutifs fusionnés).

En cas d'échec : régénérer la fiche concernée avant livraison, ne jamais livrer en l'état.
