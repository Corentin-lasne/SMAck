# Politiques des Agents avec Protocoles de Communication

## 1. Principes Généraux de Communication

### 1.1 Architecture de messaging
- **Mailbox décentralisée** : chaque agent détient une boîte aux lettres personnelle
- **Traitement des messages** : lecture systématique au début de chaque étape (`_process_incoming_messages()`)
- **Exclusivité d'action** : envoyer un message (`send_message`) est une action atomique
  - Si l'agent envoie, aucune autre action n'est exécutée sur ce tour
  - Comportement différent des actions locales (move, pick_up, drop, transform)
- **Queue de messages** : les agents enfilaient les messages en attente dans `pending_messages[]` lors de la délibération
  - Exécution différée par le modèle via `send_agent_message()`
  - Permet de queuer plusieurs messages mais un seul tour d'envoi

### 1.2 Protocoles de communication actifs
- **Découverte du disposal (rouges)** : `disposal_found` broadcast
- **Handoff vert→jaune** : séquence `carry_query` → `carry_response` → `delivery_details` + `lock_delivery`
- **Handoff jaune→rouge** : implicite via transformation et suivi d'assignation

### 1.3 Coordination locale complémentaire
- Dépôts de déchets au sol servent de signaux implicites
- Mémoire locale des robots (`waste_entries_map`, `waste_id_map`)
- Pas de gossip ; seules les observations locales et messages explicites circulent

## 2. Règles Communes de Mouvement et d'Action
## 2. Règles Communes de Mouvement et d'Action

- **Mouvements limités** : chaque agent ne peut agir que dans ses zones autorisées
- **Évitement de collisions** : fonction `_safe_move_actions()` filtre les mouvements bloquants (robot-robot)
- **Navigation** : pathfinding vers cible via `_move_toward()`, puis exploration si inatteignable
- **Timeout de portage** : si un agent porte un déchet > (grid.width + grid.height)/2 étapes
  - Force un déplacement vers la frontière Est de sa zone
  - Dépôt forcé avec action `_timeout_drop_action()`
- **Absence d'action licite** : si aucune action n'est légale, le tour est traité comme inaction (pas de crash)
- **Priorités strictes** :
  1. Message à envoyer (consomme le tour)
  2. Livraison forcée (timeout ou protocole en cours)
  3. Ramassage d'un déchet afférent
  4. Exploration/navigation

- **Priorités strictes** :
  1. Message à envoyer (consomme le tour)
  2. Livraison forcée (timeout ou protocole en cours)
  3. Ramassage d'un déchet afférent
  4. Exploration/navigation

---

## 3. Typologie des Performatives (Speech Acts)

Les performatives suivent la classification FIPA/AUML fondée sur les catégories d'actes de parole :

| Performative | Catégorie | Sens | Émetteur → Récepteur | Payload Content |
|---|---|---|---|---|
| **carry_query_empty** | Directive | Demande de prise en charge (émetteur inventaire vide après dépôt) | Green → Yellow | `query_id`, `waste_type` |
| **carry_query_not_empty** | Directive | Demande de prise en charge (émetteur garde la charge transformée) | Green → Yellow | `query_id`, `waste_type` |
| **carry_response** | Commissive | Acceptation de prise en charge | Yellow → Green | `query_id`, `accepted`, `agent_position` |
| **delivery_details** | Directive | Assignation explicite d'un déchet spécifique | Green → Yellow | `waste_id`, `waste_pos` |
| **lock_delivery** | Assertive | Information : un déchet est assigné ailleurs | Green → *Yellow* (broadcast sélectif) | `waste_id` |
| **waste_presence** | Assertive | Information : déchet détecté à la frontière | Green → Yellow (fallback) | `waste_type`, `waste_pos` |
| **disposal_found** | Assertive | Information : disposal zone découverte | Red → *Red* (broadcast) | `position` |

**Légende des catégories** :
- **Assertive** : envoie une information (constatation de fait)
- **Directive** : envoie un ordre ou une demande
- **Commissive** : s'engage sur une action future
- **Declarative** : modifie l'état du monde par l'énoncé
- **Expressive** : exprime un état interne (non utilisé ici)

**Modes de distribution** :
- **Direct** : `recipient_id` spécifique (carry_response, delivery_details)
- **Broadcast couleur** : tous les agents d'une couleur donnée (carry_query, lock_delivery, disposal_found, waste_presence)

---

## 4. Protocoles de Communication Détaillés

### 4.1 Protocole de Découverte du Disposal (Red Discovery Protocol)

**Contexte** : Les robots rouges doivent découvrir la zone de disposal et en informer tous les autres rouges.

**AUML Sequence Diagram** :

```
participant R1 : Red Agent 1
participant R2 : Red Agent 2
participant R3 : Red Agent 3

R1 -> R1: Scan eastern column\nfor radioactivity==10
R1 -> R1: disposal_zone found!
R1 -> R1: Queue broadcast\n"disposal_found"
R1 -> Model: Deliberate returns\n"send_message"
Model -> Model: Execute send_agent_message()

Model -> R1: message queued
Model -> R2: receive disposal_found\n(position=P)
Model -> R3: receive disposal_found\n(position=P)

R2 -> R2: Update known_disposal_zone = P
R3 -> R3: Update known_disposal_zone = P
```

**Étapes** :
1. **Scan initial (R1)** :
   - Navigue vers colonne Est (x = width-2)
   - Déplacement vertical aléatoire (vers haut ou bas)
   - Cherche `radioactivityAgent` avec `radioactivity==10`
   
2. **Découverte et notification** :
   - R1 détecte disposal → `known_disposal_zone = P`
   - Appelle `_queue_broadcast_to_color("red", "disposal_found", {"position": P})`
   - Retourne "send_message" (bloque toute autre action)
   
3. **Réception et mise à jour** :
   - R2, R3 reçoivent message au début du prochain step
   - Dans `_handle_message()` : détection du performative "disposal_found"
   - Extraction de position et mise à jour `known_disposal_zone`

**Propriétés** :
- **Idempotence** : vérif `if self.known_disposal_zone is None` avant envoi → un seul broadcast
- **Latence** : 1 step entre discovery et notification reçue
- **Scalabilité** : broadcast groupe ; O(n) messages pour n rouges

---

### 4.2 Protocole de Handoff Vert→Jaune (Green-Yellow Waste Handoff)

**Contexte** : Green transforme 2 verts → 1 jaune et doit le livrer à un Yellow pour transport ultérieur.

**Phases du protocole** :

#### Phase A : Préparation du Handoff
```
GREEN (carrying 2 green)
  ↓
TRANSFORM
  ↓
GREEN (carrying 1 yellow)
  ↓
NAVIGATE → eastern border of Z1
```

**Localisation** : 
- Frontière Z1/Z2 : `x = z1[2] - 1` (colonne la plus à l'est de Z1)
- Green effectue un `_deliver()` qui navigue vers cette x-coordinate

#### Phase B : Négociation Query-Response
```
GREEN → YELLOW_GROUP (broadcast)
  performative: "carry_query_not_empty"
  content: {query_id: Q1, waste_type: "yellow"}
  
  ↓ [wait 2 steps]
  
YELLOW_1 → GREEN (direct reply)
  performative: "carry_response"
  content: {query_id: Q1, accepted: True, agent_position: P1}
  
YELLOW_2 → GREEN (direct reply)
  performative: "carry_response"
  content: {query_id: Q1, accepted: True, agent_position: P2}
  
  ... [more YELLOW responses] ...
```

**AUML Sequence Diagram** :

```
participant GREEN
participant YELLOW_1
participant YELLOW_2
participant YELLOW_3
participant MODEL

GREEN -> GREEN: Reach frontier x=z1_east
GREEN -> GREEN: Queue broadcast\nCARRY_QUERY_NOT_EMPTY
GREEN -> MODEL: Deliberate returns\n"send_message"

MODEL -> MODEL: Execute send_agent_message()
MODEL -> GREEN: confirm send
MODEL -> YELLOW_1: receive carry_query
MODEL -> YELLOW_2: receive carry_query
MODEL -> YELLOW_3: receive carry_query

YELLOW_1 -> YELLOW_1: Can accept?\n(empty inventory)
YELLOW_1 -> YELLOW_1: Queue direct\nresponse to GREEN

YELLOW_2 -> YELLOW_2: Cannot accept\n(carrying yellow)
YELLOW_2 -> YELLOW_2: Ignore query

YELLOW_3 -> YELLOW_3: Queue direct\nresponse to GREEN

YELLOW_1 -> MODEL: send_agent_message()
YELLOW_3 -> MODEL: send_agent_message()

MODEL -> GREEN: receive carry_response\n(sender=Y1, pos=P1)
MODEL -> GREEN: receive carry_response\n(sender=Y3, pos=P3)

GREEN -> GREEN: Store {Q1: [(Y1,P1),\n(Y3,P3)]}
```

**Implémentation Green (`deliberate()` + `_deliver()`)** :

```python
# Step N: Reach frontier
if self.pos[0] == frontier_x and "yellow" in inv_types:
    # Send carry_query broadcast
    if self._queue_delivery_query(performative="carry_query_not_empty",
                                   receiving_group="yellow",
                                   waste_type="yellow"):
        return "send_message"  # ← Action atomique

# Step N+1: Drop waste at frontier
if self.step_last_query == self.current_step - 1:
    return "drop"

# Step N+2: Select nearest responder
if self.step_last_query == self.current_step - 2:
    candidates = self.id_and_position_carrier_response[query_id]
    if candidates:
        closest = min(candidates, key=λ: distance)
        self._queue_detail_delivery(recipient_id=closest[0])
        self._queue_lock_delivery(receiving_group="yellow")
        return "send_message"
```

**Implémentation Yellow (`_handle_message()`)** :

```python
def _handle_message(self, message):
    if message.performative == "carry_query_not_empty":
        inv = [w.waste_type for w in self.inventory]
        
        # Accept only if: inventory has exactly 1 yellow
        if len(self.inventory) == 1 and "yellow" in inv and self.assigned_waste_id is None:
            self._accept_delivery_query(message)
            # Set carry_response_lock_until to prevent multi-acceptance
            self.carry_response_lock_until = self.current_step + 2
```

**Timeline du protocole** :
- Step N : Green à frontière, envoie QUERY, bloque autres actions
- Step N+1 : Green dépôt du déchet (action fixe)
- Step N+1 : Yellows reçoivent QUERY, envoient RESPONSE
- Step N+2 : Green reçoit RESPONSE, sélectionne Yellow closest, envoie DELIVERY_DETAILS + LOCK_DELIVERY
- Step N+2 : Yellow reçoit DELIVERY_DETAILS, met à jour `assigned_waste_id` et `assigned_waste_pos`
- Step N+3+ : Yellow navigue vers waste et effectue pickup

**Cas dégénérés** :
1. **Aucun Yellow disponible** :
   - Green attend N+2, aucun répondant
   - Envoie fallback broadcast `waste_presence` (assertion de présence)
   - Yellows mettent à jour `waste_entries_map` pour visite ultérieure

2. **Réponses tardives** :
   - Les RESPONSE arrivent après N+2 : ignorées (query_id obsolète)
   - Robustesse : `carry_response_query_id` et `carry_response_lock_until` limitent les responses multiples

3. **Yellow quitte la mission** :
   - Si Yellow perd assignment (`assigned_waste_id = None`), dépôt du déchet bloque son réutilisation
   - Autres Yellows détectent via waste_entries_map

**Correction de robustesse** :
- Stockage par `query_id` : `id_and_position_carrier_response[query_id] = [(agent_id, pos), ...]`
- Lecture sécurisée : `dict.get(query_id, [])` évite KeyError
- Lock-jusqu'à-delay pour éviter flood de responses

---

### 4.3 Protocole de Portage Jaune-Rouge (Yellow-Red Waste Delivery)

**Contexte** : Yellow transforme 2 jaunes → 1 rouge et doit le livrer à la disposal zone via un Red.

**Différence avec vert→jaune** :
- Transformation est **autogénératrice** : Yellow transforme directement son inventaire
- Pas de negotiation explicite : Red absorbe tout déchet rouge à la frontière Z2/Z3
- Communication **implicite via availability** : Red cherche déchets rouges, Yellow les dépose

**Phases** :

#### Phase α : Yellow produit rouge
```
YELLOW (carrying 2 yellow)
  ↓
TRANSFORM → create 1 red
  ↓
YELLOW (carrying 1 red)
  ↓
NAVIGATE → eastern border of Z2 (x = z2[2]-1)
  ↓
DROP red at frontier
```

#### Phase β : Red détecte et transporte
```
RED (at frontier Z2/Z3 or patrol)
  ↓
PERCEPT: red waste on ground
  ↓
PICKUP red
  ↓
DIRECT_HANDOFF_MODE = always true
  ↓
NAVIGATE → disposal_zone
  ↓
DROP at disposal → waste disappears
```

**AUML Sequence Diagram** :

```
participant YELLOW
participant RED_1
participant RED_2
participant MODEL

YELLOW -> YELLOW: Transform 2 yellow\n→ 1 red
YELLOW -> YELLOW: Navigate to\nZ2 east border
YELLOW -> YELLOW: Reach border
YELLOW -> YELLOW: Item on ground\n= signal
YELLOW -> MODEL: Perform "drop"

MODEL -> MODEL: create wasteAgent\n(red) on ground

RED_1 -> RED_1: Explore Z2/Z3 frontier
RED_1 -> RED_1: Percept: red waste\nnearby
RED_1 -> RED_1: Path to waste
RED_1 -> MODEL: Perform "pick_up"

MODEL -> MODEL: Remove red from grid
MODEL -> RED_1: Inventory += red

RED_1 -> RED_1: known_disposal is set
RED_1 -> RED_1: direct_handoff until\ndisposal
RED_1 -> RED_1: Navigate →\ndisposal_zone
RED_1 -> MODEL: At disposal
RED_1 -> MODEL: Perform "drop"

MODEL -> MODEL: disposal_zone reached
MODEL -> MODEL: disposed_counts[red] += 1
MODEL -> MODEL: wasteAgent removed
```

**Implémentation** :
- **Yellow** : une fois transformé, effectue `_deliver(...waste_type="yellow"...)` vers border Z2
  - Aucune query ; pas d'attente de confirmation
  - Le dépôt du rouge au sol EST la communication
  
- **Red** : patrouille Z2/Z3, détecte déchets rouges/jaunes/verts (à la frontière seulement)
  - Pickup automatique selon `_can_add_waste_type()`
  - Une fois porté → direct_handoff_mode = toujours actif
  - Navigation implicite vers `known_disposal_zone`

**Propriétés** :
- **Asynchrone** : Red n'a pas besoin de receipt de Yellow
- **Robustesse** : dépôt au sol persiste jusqu'à pickup
- **Scalabilité** : plusieurs Reds peuvent concurrencer pour un même rouge

---

### 4.4 Protocole de Lock et Évitement de Duplication (Lock & Conflict Avoidance)

**Contexte** : Plusieurs Yellows pourraient converger vers le même déchet en frontière si pas de synchronisation.

**Mécanisme** :

1. **Green → Yellow : LOCK_DELIVERY broadcast**
   ```
   After selecting Yellow_closest from carries_response:
   
   Green sends to ALL yellows:
     performative: "lock_delivery"
     content: {waste_id: wid}
   ```

2. **Yellow reçoit LOCK_DELIVERY** :
   ```python
   def _handle_message(self, message):
       if message.performative == "lock_delivery":
           waste_id = message.content.get("waste_id")
           # Only lock if not already assigned to us
           if waste_id != self.assigned_waste_id:
               self.locked_waste_ids.add(waste_id)
   ```

3. **Yellow avant pickup** :
   ```python
   def _can_add_waste_type(self, waste_type, waste_id, waste_pos):
       if waste_id in self.locked_waste_ids:
           return False  # ← Refuse pickup
       return ...
   ```

**Timeline** :
- Step N : Green envoie DELIVERY_DETAILS (Y_closest) + LOCK_DELIVERY (all yellows)
- Step N+1 : Y_closest reçoit DETAILS → `assigned_waste_id = wid`
- Step N+1 : Y_other reçoit LOCK → `locked_waste_ids.add(wid)`
- Step N+1+ : Y_other refuse pickup de ce `wid` (vérifie avant `_can_add_waste_type()`)

**Correction de robustesse** :
- Vérification dans LOCK handler : `if waste_id != self.assigned_waste_id:` 
  - Évite de se verrouiller soi-même si LOCK reçu après DETAILS

---

### 4.5 Protocole Fallback : Waste Presence Broadcast

**Contexte** : Si aucun Yellow ne répond à la query, Green ne peut pas assigner. Fallback = broadcast assertion.

**Déclenchement** :
```python
# In _deliver() after Step N+2 delay:
if not candidates:  # Aucune carry_response reçue
    self._queue_broadcast_waste_presence(receiving_group="yellow")
```

**Contenu** :
```python
performative: "waste_presence"
content: {waste_type: "yellow", waste_pos: (border_x, y)}
```

**Réception Yellow** :
```python
if message.performative == "waste_presence":
    waste_type = message.content.get("waste_type")
    waste_pos = message.content.get("waste_pos")
    self.waste_entries_map[waste_pos] = waste_type
    # Update knowledge → future pickup planning
```

**Utilité** :
- **Information passive** : aucune obligation de réponse
- **Planning long-terme** : Yellow met à jour sa carte et peut planifier visite future
- **Robustesse** : survit si Yellow encombré temporairement

---

## 5. Contraintes Spécifiques par Rôle

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
