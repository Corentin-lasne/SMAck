# Policies des Agents (Etape sans Communication)

## 1. Principe general
- Aucun message entre agents.
- Coordination uniquement par l'environnement (dechets poses au sol).
- Chaque agent decide localement via ses percepts, sa memoire locale (`known_map`, `waste_map`) et ses contraintes de zone.

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
- Contrainte frontiere Z1/Z2:
    si inventaire vide, il ne peut pas ramasser un vert sur cette frontiere.
    s'il a deja un vert en inventaire, il peut ramasser ce vert de frontiere.

## 4. Agent Jaune (Zones 1 et 2)
- Types ramassables: vert et jaune.
- Ne ramasse jamais de rouge au sol.
- Vert autorise uniquement sur la frontiere Z1/Z2 et uniquement inventaire vide.
- Si un vert est pris: `direct_handoff_mode` obligatoire, livraison directe a la frontiere Est Z2, puis `drop`.
- Jaune autorise dans sa zone et sur frontiere Z1/Z2.
- Contrainte frontiere Z2/Z3 pour le jaune:
    il ne peut ramasser un jaune sur cette frontiere que s'il a deja un jaune en inventaire.
- Transformation: 2 jaunes -> 1 rouge (dans l'inventaire).
- Le rouge transporte par un jaune vient uniquement de cette transformation (jamais pickup au sol).

## 5. Agent Rouge (Zones 1, 2, 3)
- Capacite: 1.
- Types ramassables:
    - rouge: partout dans ses zones autorisees.
    - vert/jaune: uniquement sur la frontiere Z2/Z3.
- `direct_handoff_mode` obligatoire des qu'un dechet est porte.
    destination unique: disposal zone.
- Depot au disposal:
    tout dechet depose (quelle que soit sa couleur) est supprime definitivement.
    il ne peut donc pas etre repris ensuite.

## 6. Rappel IDs
- Chaque robot a un `agent_id` unique.
- Chaque dechet a un `waste_id` unique (creation initiale + dechets issus de transformations).
