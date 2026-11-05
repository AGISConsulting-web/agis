---
name: crea-skill
description: Usala quando Loffre chiede di "imparare" una procedura, quando la stessa richiesta in più passi si ripete, o quando chiede ad AGIS di creare una nuova skill.
---

# Creare una nuova skill per AGIS

Una skill è una cartella `.claude/skills/<nome>/` con un file `SKILL.md`. Claude Code la
carica da solo quando la descrizione corrisponde alla richiesta. È il modo in cui AGIS
diventa più capace nel tempo.

## Procedura
1. **Riconosci la procedura**: quali passi si ripetono, quali dati servono in ingresso,
   cosa si consegna alla fine, quali regole o preferenze di Loffre valgono.
2. **Proponi prima di scrivere**: descrivi a Loffre in 3-5 righe la skill (nome, quando si
   usa, passi principali) e chiedi conferma.
3. **Dopo il suo ok**, crea `.claude/skills/<nome-in-kebab-case>/SKILL.md` con:
   - frontmatter con `name` e una `description` di una frase che dica *quando* usarla;
   - i passi numerati, concreti, con il formato di consegna atteso;
   - le regole da rispettare (cosa non fare, cosa chiedere prima).
4. **Annota** in `memoria/note.md` una riga: data, nome della skill, a cosa serve.

## Regole
- Mai skill che inviano, pubblicano, pagano o cancellano senza conferma.
- Mai inserire password, chiavi o dati personali dentro una skill.
- Se una skill esistente fa già quasi la stessa cosa, proponi di migliorarla invece di crearne una nuova.
