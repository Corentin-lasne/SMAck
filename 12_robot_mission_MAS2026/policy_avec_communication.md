# Policies des Agents (Etape avec communication rouge)

## 1. Principe general
- Une mailbox existe pour tous les robots et les messages recus sont traites en debut de step.
- L'envoi d'un message (`send_message`) est une action a part entiere: si l'agent envoie, il ne fait aucune autre action sur ce tour.
- Pour cette etape, la communication active est utilisee par:
    - les rouges (`disposal_found`),
    - le protocole de handoff vert -> jaune (`carry_query`, `carry_response`, `delivery_details`, `lock_delivery`).
- Coordination locale maintenue en parallele: dechets poses au sol + memoire locale.

## 2. Regles communes
- Mouvements autorises uniquement dans les zones de l'agent.
- Evitement des collisions robot-robot (`_safe_move_actions`).
- Navigation cible avec `_move_toward`, puis exploration si besoin.
- Timeout de portage: si un agent garde un dechet pendant (grid.width + grid.height)/2, il va a sa frontiere Est et drop.
- Si une policy ne retourne aucune action (encadré de 4 agents donc pas d'action licite), le modele traite cela comme un tour sans action (pas de crash).

## 3. Agent Vert (Zone 1 uniquement)
- Types ramassables: vert uniquement.
- Ne ramasse jamais de jaune au sol.
- Transformation: 2 verts -> 1 jaune (dans l'inventaire).
- `direct_handoff_mode` actif uniquement quand il porte ce jaune transforme.
    destination directe: frontiere Est Z1, puis `drop`.
- Protocole de livraison du jaune transforme a la frontiere Z1/Z2:
    - envoi d'un broadcast `carry_query` aux jaunes eligibles,
    - attente des `carry_response`,
    - `drop` du jaune a la frontiere,
    - selection du jaune repondant le plus proche,
    - envoi d'un `delivery_details` au jaune selectionne (assignation explicite du `waste_id`).
- Correctif robustesse: les reponses `carry_response` sont conservees par `query_id` jusqu'a consommation par le vert (pas d'effacement global a chaque step).
- Correctif robustesse: la lecture des reponses est securisee (`dict.get`) pour eviter les `KeyError` si aucune reponse n'est disponible pour une requete.
- Contrainte frontiere Z1/Z2:
    si inventaire vide, il ne peut pas ramasser un vert sur cette frontiere.
    s'il a deja un vert en inventaire, il peut ramasser ce vert de frontiere.

## 4. Agent Jaune (Zones 1 et 2)
- Types ramassables: vert et jaune.
- Ne ramasse jamais de rouge au sol.
- Vert autorise uniquement sur la frontiere Z1/Z2 et uniquement inventaire vide.
- Si un vert est pris: `direct_handoff_mode` obligatoire, livraison directe a la frontiere Est Z2, puis `drop`.
- Jaune autorise dans sa zone et sur frontiere Z1/Z2.
- Reception `carry_query`:
    - un jaune peut repondre via `carry_response` s'il est dans un etat compatible de prise en charge,
    - la prise en charge ciblee se fait ensuite via `delivery_details` (qui renseigne `assigned_waste_id` et `assigned_waste_pos`).
- Reception `lock_delivery`:
    - un dechet est ajoute a `locked_waste_ids` sauf s'il est deja celui assigne au robot courant.
- Contrainte frontiere Z2/Z3 pour le jaune:
    il ne peut ramasser un jaune sur cette frontiere que s'il a deja un jaune en inventaire.
- Transformation: 2 jaunes -> 1 rouge (dans l'inventaire).
- Le rouge transporte par un jaune vient uniquement de cette transformation (jamais pickup au sol).

## 5. Agent Rouge (Zones 1, 2, 3)
- Capacite: 1.
- Types ramassables:
    - rouge: partout dans ses zones autorisees.
    - vert/jaune: uniquement sur la frontiere Z2/Z3.
- Phase initiale de communication:
    - Chaque rouge va vers la colonne Est et la scanne verticalement.
    - Le premier rouge qui detecte le disposal memorise sa position et programme un broadcast `disposal_found` a tous les rouges.
    - Ce broadcast consomme le tour (action `send_message`).
    - Les autres rouges lisent ce message en debut de step, memorisent la position, puis reprennent la policy normale.
- `direct_handoff_mode` obligatoire des qu'un dechet est porte.
    destination unique: disposal zone.
- Depot au disposal:
    tout dechet depose (quelle que soit sa couleur) est supprime definitivement.
    il ne peut donc pas etre repris ensuite.

## 6. Rappel IDs
- Chaque robot a un `agent_id` unique.
- Chaque dechet a un `waste_id` unique (creation initiale + dechets issus de transformations).

## 7. Observabilite simulation (UI)
- Etiquette des dechets: `waste_id [A<agent_id>]` quand un owner assigne est connu.
- Etiquette des robots:
    - `A<agent_id>` si pas d'assignation en cours,
    - `A<agent_id> | W<assigned_waste_id>` si une assignation est active.
- Ces marqueurs permettent de verifier visuellement que l'assignation post-handoff est bien materialisee dans la simulation.
