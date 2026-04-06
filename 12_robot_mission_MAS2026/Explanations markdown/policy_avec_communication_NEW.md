# Politiques des Agents avec Protocoles de Communication (AUML)

## Table des Matières
1. [Principes Généraux](#1-principes-généraux-de-communication)
2. [Règles Communes](#2-règles-communes-de-mouvement-et-daction)
3. [Performatives (Speech Acts)](#3-tableau-des-performatives-et-actes-de-parole)
4. [Protocoles Détaillés](#4-protocoles-de-communication-détaillés)
5. [Spécifications par Rôle](#5-spécifications-par-rôle)
6. [Identificateurs](#6-identificateurs)
7. [Observabilité](#7-observabilité-simulation-ui)

---

## 1. Principes Généraux de Communication

### 1.1 Architecture de Messaging
- **Mailbox décentralisée** : chaque agent détient une boîte aux lettres personnelle
- **Traitement des messages** : lecture systématique au début de chaque étape (`_process_incoming_messages()`)
- **Exclusivité d'action** : envoyer un message (`send_message`) est une action atomique
  - Si l'agent envoie, aucune autre action n'est exécutée sur ce tour
  - Comportement différent des actions locales (move, pick_up, drop, transform)
- **Queue de messages** : les agents enfilent les messages en attente dans `pending_messages[]` lors de la délibération
  - Exécution différée par le modèle via `send_agent_message()`
  - Permet de queuer plusieurs messages mais exécution d'un seul tour d'envoi

### 1.2 Protocoles de Communication Actifs
1. **Découverte du disposal (rouges)** : `disposal_found` broadcast
2. **Handoff vert→jaune** : séquence `carry_query` → `carry_response` → `delivery_details` + `lock_delivery`
3. **Handoff jaune→rouge** : implicite via transformation et suivi d'assignation
4. **Protocole de lock** : prévention des doublons d'assignation
5. **Fallback waste_presence** : assertion de présence en cas de non-réponse

### 1.3 Coordination Locale Complémentaire
- Dépôts de déchets au sol servent de signaux implicites
- Mémoire locale des robots (`waste_entries_map`, `waste_id_map`)
- Pas de gossip ; seules les observations locales et messages explicites circulent

---

## 2. Règles Communes de Mouvement et d'Action

- **Mouvements limités** : chaque agent n'agit que dans ses zones autorisées
- **Évitement de collisions** : fonction `_safe_move_actions()` filtre les mouvements d'agents
- **Navigation optimale** : pathfinding vers cible via `_move_toward()`, puis exploration si cible inatteignable
- **Timeout de portage** : si un agent porte un déchet > (grid.width + grid.height)/2 étapes
  - Force déplacement vers la frontière Est de sa zone
  - Dépôt forcé avec action `_timeout_drop_action()`
- **Gestion du vide** : si aucune action n'est légale, le tour est traité comme inaction (pas de crash)
- **Priorités strictes décisionnelles** :
  1. Message à envoyer (consomme le tour entier)
  2. Livraison forcée (timeout ou séquence protocole en cours)
  3. Ramassage d'un déchet cible
  4. Navigation puis exploration aléatoire

---

## 3. Tableau des Performatives et Actes de Parole

### Classification par Catégorie FIPA/AUML

| **Performative** | **Catégorie** | **Signification** | **Émetteur → Récepteur** | **Contenu** | **Mode** |
|---|---|---|---|---|---|
| `carry_query_empty` | Directive | Demande prise en charge (émetteur vide post-dépôt) | Green → Yellow  ou Yellow → Red | `query_id`, `waste_type` | Broadcast |
| `carry_query_not_empty` | Directive | Demande prise en charge (émetteur avec un objet du même type) | Green → Yellow  ou Yellow → Red | `query_id`, `waste_type` | Broadcast |
| `carry_response` | Commissive | Acceptation de prise en charge | Yellow → Green ou Red → Yellow | `query_id`, `accepted`, `agent_position` | Direct |
| `delivery_details` | Directive | Assignation explicite d'un déchet cible | Green → Yellow ou Yellow → Red | `waste_id`, `waste_pos` | Direct |
| `lock_delivery` | Assertive | Assertion : déchet assigné à un autre agent | Green → Yellow  ou Yellow → Red  | `waste_id` | Broadcast |
| `waste_presence` | Assertive | Assertion : déchet détecté à la frontière | Green → Yellow  ou Yellow → Red  | `waste_type`, `waste_pos`, `waste_id` | Broadcast |
| `disposal_found` | Assertive | Assertion : zone de disposal découverte | Red → Red  | `position` | Broadcast |

---

## 4. Protocoles de Communication Détaillés

### 4.1 Protocole de Découverte du Disposal (Red Discovery Protocol)

**Contexte** : Les robots rouges doivent découvrir la zone de disposal (radioactivity=10) et en informer tous les autres rouges.

**Localisation** : position aléatoire sur la colonne la plus à l'est (x = width-1)

#### Diagramme AUML

```
RED_1 → Scan eastern column looking for radioactivity=10
  ↓ (Multiple steps)
RED_1 : discovered disposal_zone at position P
  ↓
RED_1 → _queue_broadcast_to_color("red", "disposal_found", {"position": P})
  ↓
RED_1 → Model: return "send_message"
  ↓ [Step N → N+1]
Model → RED_2: receive "disposal_found" with position P
Model → RED_3: receive "disposal_found" with position P
  ↓
RED_2 → _handle_message(): update known_disposal_zone = P
RED_3 → _handle_message(): update known_disposal_zone = P
  ↓
RED_1, RED_2, RED_3 → Now can start exploring knowing the disposal location
```

#### Propriétés du Protocole

- **Idempotence** : vérification `if self.known_disposal_zone is None` avant envoi → un seul broadcast pour tous les Red
- **Latence** : 1 step entre discovery et notification reçue (asynchrone)
- **Scalabilité** : broadcast groupe ; O(n) messages pour n rouges
---

### 4.2 Protocole de Handoff Vert→Jaune (Green-Yellow Dynamic Handoff)

**Contexte** : Green transforme 2 verts → 1 jaune et doit le livrer à un Yellow pour transport ultérieur vers Yellow/Red.

**Localisation frontière** : `x = z1_east = z1[2] - 1` (colonne la plus à l'est de Z1)

#### Phase A : Préparation

```
GREEN carries 2 green
  ↓ [action: "transform"]
GREEN carries 1 yellow (+ maybe 0 more)
  ↓ [deliberate() → _deliver(...waste_type="yellow"...)]
GREEN navigates toward border (x = z1_east)
  ↓
GREEN reaches border_pos
```

#### Phase B : Négociation (Query-Response)

**Conditions initiales** :
- Green at frontier with yellow in inventory
- Should send carry_query

**Step N : Green sends QUERY**

```
GREEN:deliberate()
  ├─ Check _send_if_pending_action() → None
  ├─ Check timeout_drop_action() → None (freshly carrying)
  ├─ Check if "yellow" in inventory → YES
  ├─ Call _deliver(target_x=z1_east, performative="carry_query_not_empty",
                    receiving_group="yellow", waste_type="yellow")
  │    ├─ if pos[0] == z1_east:
  │    │    ├─ _queue_delivery_query(...) → queues broadcast
  │    │    │    └─ _queue_broadcast_to_color("yellow", "carry_query_not_empty", ...)
  │    │    │    └─ Sets: id_last_query, step_last_query, query_sent_for_batch
  │    │    └─ return "send_message"  ← THIS BLOCKS OTHER ACTIONS
  │
  └─ return "send_message"

Model.send_agent_message(GREEN):
  ├─ Process pending_messages[] with broadcast_to_color()
  ├─ For each Yellow agent:
  │    └─ send_message(GREEN.agent_id, YELLOW.agent_id, "carry_query_not_empty", {...})
  │       └─ Add to YELLOW.mailbox._unread_messages
  └─ Clear pending_messages[]
```

**Step N : Yellows receive & process QUERY**

```
YELLOW_1:step_agent():
  ├─ _process_incoming_messages():
  │    ├─ new_messages = model.get_new_messages(YELLOW_1.agent_id)
  │    └─ _handle_message(message):
  │         ├─ if message.performative == "carry_query_not_empty":
  │         │    ├─ inv_types = [w.waste_type for w in inventory]
  │         │    ├─ can_accept = len(inventory)==1 and "yellow" in inv_types and assigned_waste_id==None
  │         │    ├─ if can_accept → _accept_delivery_query(message):
  │         │    │    ├─ if current_step >= carry_response_lock_until:  ← Prevent multi-response
  │         │    │    │    ├─ _queue_direct_message(sender_id=GREEN.agent_id,
  │         │    │    │    │                        performative="carry_response",
  │         │    │    │    │                        content={query_id:..., accepted:True, agent_position:...})
  │         │    │    │    └─ carry_response_lock_until = current_step + 2  ← Cooldown
  │         │    │    │    └─ blocked_from_pickup_until = current_step + 2
  │         │    │    └─ return

YELLOW_2:step_agent():
  ├─ _process_incoming_messages():
  │    ├─ _handle_message(message):
  │         ├─ if message.performative == "carry_query_not_empty":
  │         │    ├─ inv_types = [...] → NOT "yellow" (carrying red, e.g.)
  │         │    ├─ can_accept = FALSE
  │         │    └─ IGNORE query (no response sent)
```

**AUML Sequence Diagram (Steps N to N+2)**

```
participant GREEN
participant YELLOW_1
participant YELLOW_2
participant YELLOW_3
participant MODEL

GREEN -> GREEN: At frontier x=z1_east\n+ "yellow" in inventory
GREEN -> GREEN: _queue_delivery_query()\n+ "carry_query_not_empty"
GREEN -> MODEL: deliberate() return\n"send_message"

MODEL -> MODEL: Execute send_agent_message(GREEN)
MODEL -> YELLOW_1: message delivered
MODEL -> YELLOW_2: message delivered
MODEL -> YELLOW_3: message delivered

YELLOW_1 -> YELLOW_1: Parse carry_query_not_empty\nInventory = [yellow]\nNo assignment
YELLOW_1 -> YELLOW_1: _accept_delivery_query()
YELLOW_1 -> YELLOW_1: _queue_direct_message(carry_response)\nto GREEN

YELLOW_2 -> YELLOW_2: Parse carry_query_not_empty\nInventory = [red]\nDecline

YELLOW_3 -> YELLOW_3: Parse carry_query_not_empty\nInventory = [yellow]\nNo assignment
YELLOW_3 -> YELLOW_3: _accept_delivery_query()
YELLOW_3 -> YELLOW_3: _queue_direct_message(carry_response)\nto GREEN

YELLOW_1 -> MODEL: send_agent_message(YELLOW_1)
YELLOW_3 -> MODEL: send_agent_message(YELLOW_3)

MODEL -> GREEN: message received from YELLOW_1
MODEL -> GREEN: message received from YELLOW_3

GREEN -> GREEN: Store responses by query_id:\nid_and_position_carrier_response[Q1]\n= [(Y1, pos1), (Y3, pos3)]
```

#### Phase C : Sélection et Lock (Step N+2)

**Dans GREEN.deliberate() après Step N+1 delay** :

```python
# Step N+2: Select nearest responder + send Lock
if self.step_last_query == self.current_step - 2:
    candidates = self.id_and_position_carrier_response.get(self.id_last_query, [])
    
    if candidates:
        # Calculate distance from DROP position to each responder
        closest = min(candidates, key=lambda c: manhattan(self.pos, c[1]))
        closest_agent_id = closest[0]
        
        # Queue delivery details (private message)
        self._queue_detail_delivery(recipient_id=closest_agent_id)
        
        # Queue lock broadcast to all other yellows
        self._queue_lock_delivery(receiving_group="yellow")
        
        return "send_message"  ← Block other actions

    else:  # No responses → fallback
        self._queue_broadcast_waste_presence(receiving_group="yellow")
        return "send_message"
```

**Step N+2 : Yellows receive LOCK & DETAILS**

```
YELLOW_1 (closest):
  ├─ _handle_message("delivery_details" from GREEN):
  │    ├─ waste_id = message.content.get("waste_id")
  │    ├─ waste_pos = message.content.get("waste_pos")
  │    ├─ self.assigned_waste_id = waste_id
  │    ├─ self.assigned_waste_pos = waste_pos
  │    └─ return

YELLOW_2:
  ├─ _handle_message("lock_delivery" from GREEN):
  │    ├─ waste_id = message.content.get("waste_id")
  │    ├─ if waste_id != self.assigned_waste_id:  ← Only if not assigned to us
  │    │    └─ self.locked_waste_ids.add(waste_id)
  │    └─ return

YELLOW_3:
  ├─ _handle_message("lock_delivery" from GREEN):
  │    ├─ waste_id = message.content.get("waste_id")
  │    ├─ if waste_id != self.assigned_waste_id:
  │    │    └─ self.locked_waste_ids.add(waste_id)
  │    └─ return
```

#### Phase D : Transport et Livraison

**YELLOW_1 après assignation** :

```python
def deliberate():
    # Priority: if assigned_waste_pos is set, navigate there
    if self.assigned_waste_pos is not None:
        action = self._move_toward(self.assigned_waste_pos)
        if action:
            return action
    
    # Once at assigned position, perform pickup if waste is there
    current_contents = self.percepts["surrounding"][self.pos]
    if any(isinstance(obj, wasteAgent) and obj.waste_id == self.assigned_waste_id 
           for obj in current_contents):
        return "pick_up"
```

**Yellow carries yellow then transforms to red** → séquence implicite yellow-to-red

#### Timeline Complète

| Step | Green | Yellow_1 | Yellow_2 | Yellow_3 | Action |
|---|---|---|---|---|---|
| N-1 | Carrying yellow | Carrying yellow | Carrying red | Carrying yellow | Both navigate |
| N | At frontier, send QUERY | Receive QUERY | Receive QUERY | Receive QUERY | GREEN: "send_message" |
| N+1 | At frontier (wait) | Accept → send RESPONSE | Ignore | Accept → send RESPONSE | Y1,Y3: "send_message" |
| N+2 | Receive RESPONSE(s), select Y_1, send DETAILS+LOCK | Receive DETAILS (assigned) | Receive LOCK (locked) | Receive LOCK (locked) | GREEN: "send_message" |
| N+3+ | Drop + explore | Navigate to waste_pos | Continue exploration | Continue exploration | Y1 moves, others roam |
| N+k | - | Pickup yellow at frontier | - | - | Y1: "pick_up" |
| N+k+1+ | - | Transform yellow→red, livrer Red | - | - | Y1: at Z2 boundary |

#### Cas Dégénérés

**1. Aucun Yellow disponible (Step N+2)** :
```python
if not candidates:
    self._queue_broadcast_waste_presence(receiving_group="yellow")
```
→ Fallback assertive broadcast (section 4.5)

**2. Réponses tardives** :
- CARRY_RESPONSE arrive après N+2 : `query_id` obsolète, ignorée

**3. Yellow perd assignment** :
- Si `assigned_waste_id = None`, le déchet au sol attend
- Autre Yellow le découvre via `waste_entries_map` et visite ultérieure

**4. Message reordering** :
- Correction `if waste_id != self.assigned_waste_id` dans lock handler
- Évite de se verrouiller après avoir reçu DETAILS

---

### 4.3 Protocole de Portage Jaune→Rouge (Yellow-Red Implicit Handoff)

**Contexte** : Yellow transforme 2 jaunes → 1 rouge et doit le livrer à un Red pour disposal.

**Différence clé vs vert→jaune** :
- Pas de query-response explicite
- Red absorbe **tout** déchet rouge à la frontière Z2/Z3
- Communication via dépôt au sol (signaling implicite)

#### Phases

**Phase α : Yellow crée rouge**

```
YELLOW carries 2 yellow
  ↓ [action: "transform"]
YELLOW carries 1 red
  ↓ [deliberate() → _deliver(...waste_type="yellow"...)]
  ↓  Navigate to Z2 east border (x = z2_east = z2[2]-1)
  ↓
YELLOW at border
  ↓ [action: "drop"]
RED (physical object) placed on grid
```

**Phase β : Red détecte et transporte**

```
RED at frontier or patrolling Z2/Z3
  ↓
RED percept: red waste on ground
  ├─ Can pickup? YES (waste_type=="red")
  ├─ Do not exceed capacity? YES (capacity=1)
  └─ Not locked/assigned elsewhere? YES
  ↓
RED [action: "pick_up"]
  ↓
RED inventory += red waste
RED direct_handoff_mode = active (until disposal)
  ↓
RED navigate → known_disposal_zone
  ↓
RED at disposal_zone
  ↓ [action: "drop"]
disposal_zone reached → waste disappears
disposed_counts["red"] += 1
```

#### AUML Diagram

```
participant YELLOW
participant RED_1
participant RED_2
participant MODEL
participant GRID

YELLOW -> YELLOW: Transform 2 yellow → 1 red\n(in inventory)
YELLOW -> YELLOW: Navigate to Z2 east border
YELLOW -> YELLOW: Reach border pos
YELLOW -> MODEL: Action "drop"

MODEL -> GRID: Remove red from YELLOW inventory
MODEL -> GRID: Place red wasteAgent on ground

RED_1 -> RED_1: Patrol Z2/Z3 frontier
RED_1 -> RED_1: Percept: red waste nearby
RED_1 -> RED_1: Path feasible to waste
RED_1 -> MODEL: Action "pick_up"

MODEL -> GRID: Remove red from ground
MODEL -> RED_1: Add to inventory

RED_1 -> RED_1: direct_handoff_mode\n= always
RED_1 -> RED_1: known_disposal_zone\nset (from broadcast)
RED_1 -> RED_1: Navigate → disposal_zone
RED_1 -> RED_1: Reach disposal_zone
RED_1 -> MODEL: Action "drop"

MODEL -> GRID: waste removed\ndisposed_counts["red"]++
```

#### Propriétés

- **Asynchrone** : Red n'attend pas Yellow ; seulement perception passive
- **Robustesse** : déchet persiste au sol jusqu'à pickup
- **Concurrence** : plusieurs Reds peuvent compétitionner pour le même rouge
- **Latence** : délai indéterminé entre drop et pickup

---

### 4.4 Protocole de Lock et Évitement de Duplication

**Contexte** : Plusieurs Yellows pourraient converger vers le même déchet en frontière Z1/Z2 si pas de synchronisation.

#### Mécanisme

**Step 1 : Green sélectionne Yellow_closest et envoie**

```python
# In Green._deliver() at Step N+2:
closest = min(candidates, key=lambda c: manhattan(self.pos, c[1]))

self._queue_detail_delivery(recipient_id=closest[0])
self._queue_lock_delivery(receiving_group="yellow")

return "send_message"
```

**Step 2 : Tous les Yellows reçoivent**

```python
# Yellow_closest:
def _handle_message(message):
    if message.performative == "delivery_details":
        waste_id = message.content.get("waste_id")
        assigned_waste_id = waste_id      ← Marked as assigned
        assigned_waste_pos = pos
        locked_waste_ids.discard(waste_id)  ← Unlock self if previously locked
        
# Yellow_other:
def _handle_message(message):
    if message.performative == "lock_delivery":
        waste_id = message.content.get("waste_id")
        if waste_id != self.assigned_waste_id:  ← Safety check
            locked_waste_ids.add(waste_id)

# All Future Pickup Attempts:
def _can_add_waste_type(self, waste_type, waste_id, ...):
    if waste_id in self.locked_waste_ids:
        return False  ← REFUSE pickup
    return ...
```

#### Timeline

| Step | Y_closest | Y_other | Waste Status |
|---|---|---|---|
| N+1 | Received RESPONSE | Received RESPONSE | On grid at frontier |
| N+2 | Received DETAILS (assigned) | Received LOCK (locked) | On grid, "claimed" |
| N+3+ | Navigate to frontier | Cannot pickup (locked) | On grid, waiting |
| N+k | Pickup (assigned) | Still locked | In inventory |

#### Robustesse

- **Vérification dans LOCK handler** : `if waste_id != self.assigned_waste_id:`
  - Prevents self-locking after DETAILS receipt (message reorder edge case)
- **Discard in DETAILS handler** : `locked_waste_ids.discard(waste_id)`
  - If LOCK arrives before DETAILS, this clears the lock

---

### 4.5 Protocole Fallback : Waste Presence Broadcast

**Contexte** : Si aucun Yellow ne répond à la query, Green ne peut pas assigner. Fallback = passive assertion.

#### Déclenchement

```python
# In Green._deliver() after Step N+2 delay:
candidates = self.id_and_position_carrier_response.get(query_id, [])

if not candidates:  # No carry_response received
    self._queue_broadcast_waste_presence(receiving_group="yellow")
    return "send_message"
```

#### Contenu

```python
performative: "waste_presence"
content: {
    waste_type: "yellow",
    waste_pos: (border_x, y)  # Where waste was dropped
}
mode: "broadcast_color"
```

#### Réception et Traitement

```python
# Yellow receiving waste_presence:
def _handle_message(self, message):
    if message.performative == "waste_presence":
        waste_type = message.content.get("waste_type")
        waste_pos = message.content.get("waste_pos")
        
        # Update knowledge base for future planning
        self.waste_entries_map[waste_pos] = waste_type
        # No commitment; no assignment
```

#### Utilité

- **Information passive** : aucune obligation de réponse
- **Planning long-terme** : Yellow peut planifier visite ultérieure si congestion
- **Robustesse** : persiste dans waste_entries_map si Yellow prend d'autres tâches temporairement
- **Décentralisation** : Green ne "bloque" pas en attendant reconfirmation

---

## 5. Spécifications par Rôle

### 5.1 Agent Vert (Green Agent - Zone Z1 uniquement)

**Capacité max** : 2

**Types de déchets ramassables** :
- Vert : partout dans Z1

**Types de déchets NON-ramassables** :
- Jaune depuis le sol (jamais)
- Rouge depuis le sol (jamais)

**Transformation** :
- 2 verts → 1 jaune (dans inventaire)

**Communications initiées** :
- `carry_query_not_empty` (après transformation jaune, à frontière Z1/Z2)
- `delivery_details` (direct to selected Yellow)
- `lock_delivery` (broadcast group)
- `waste_presence` (fallback si no response)

**Contrainte frontière Z1/Z2** :
- Si inventaire vide : ne peut PAS ramasser vert sur frontière
- Si inventaire ≥ 1 vert : peut ramasser vert supplémentaire de frontière
  - Rationale : permet accumulation 2 verts avant transformation

**Direct Handoff Mode** :
- Activé après transformation jaune
- Destination forcée : frontière Est Z1
- Drop au border, puis attendre assignation/réponses

**Priorités délibération** :
1. Send message (si pending)
2. Timeout drop (si carrying > limit)
3. Delivery protocol (if jaune in inventory or post-query delay)
4. Transform (if 2+ green in inventory)
5. Pickup green (if available)
6. Navigate to green targets (if known)
7. Explore frontier

---

### 5.2 Agent Jaune (Yellow Agent - Zones Z1 et Z2)

**Capacité max** : 2

**Types de déchets ramassables** :
- Vert : UNIQUEMENT frontière Z1/Z2, UNIQUEMENT si inventaire vide
- Jaune : partout dans Z1/Z2 ET frontière Z2/Z3 (sous conditions)
- Rouge : JAMAIS depuis le sol

**Types de déchets NON-ramassables** :
- Rouge depuis le sol (jamais ; yellow carries red seulement après transformation)

**Transformation** :
- 2 jaunes → 1 rouge (dans inventaire)

**Communications reçues** :
- `carry_query_not_empty` ou `carry_query_empty` (from Green)
  - Peut répondre par `carry_response` si conditions acceptées
- `delivery_details` (private from Green)
  - Mise à jour assignment : `assigned_waste_id`, `assigned_waste_pos`
- `lock_delivery` (broadcast from Green)
  - Mise à jour lock : `locked_waste_ids.add(waste_id)`
- `disposal_found` (from Red)
  - Mise à jour knowledge : `known_disposal_zone`

**Réception protocole Green→Yellow** :
- Si reçoit `carry_query_*` : peut répondre `carry_response` si
  - For `carry_query_not_empty` : inventaire == 1, waste_type == "yellow", no assignment
  - For `carry_query_empty` : inventaire == 0, no assignment
  - Set cooldown `carry_response_lock_until` pour éviter multiple responses
  
- Si reçoit `delivery_details` : extrait `waste_id` et `waste_pos`
  - Set `assigned_waste_id` et `assigned_waste_pos`
  - Discard from `locked_waste_ids` si présent
  
- Si reçoit `lock_delivery` : extrait `waste_id`
  - Si `waste_id != assigned_waste_id` : add to `locked_waste_ids`

**Contrainte frontière Z1/Z2** :
- Vert autorisé UNIQUEMENT si inventaire vide
  - Rationale : Green crée jaune juste là; Yellow l'absorbe et traverse à Z2

**Contrainte frontière Z2/Z3** :
- Jaune autorisé pour pickup UNIQUEMENT si inventaire already contains yellow
  - Rationale : Yellow accumule 2 jaunes avant transformation

**Direct Handoff Mode** (si porte vert transformé) :
- Destination forcée : frontière Est Z2
- Après drop, abandon de vert → inventory redevient vide
- Prêt pour nouvelle assignation verte OU jaune farming

**Direct Handoff Mode** (si porte rouge transformé) :
- Naviguer vers Z2/Z3 boundary
- Drop rouge pour que Red le ramasse
- Aucune query ; signaling implicite

**Priorités délibération** :
1. Send message (si pending)
2. Timeout drop (si carrying > limit)
3. Resolve assigned greenish waste (navigate to assigned_waste_pos)
4. Direct handoff red transport (if rouge in inventory)
5. Transform (if 2 yellow in inventory)
6. Pickup waste (if available & eligible)
7. Navigate to targets
8. Explore frontier

---

### 5.3 Agent Rouge (Red Agent - Zones Z1, Z2, Z3)

**Capacité max** : 1

**Types de déchets ramassables** :
- Rouge : partout dans Z1/Z2/Z3
- Vert/Jaune : UNIQUEMENT frontière Z2/Z3

**Types de déchets NON-ramassables** :
- Green/Yellow depuis le sol en zone intérieure

**Transformation** :
- Aucune (transport pur vers disposal)

**Communications initiées** :
- `disposal_found` (broadcast group après découverte)

**Communications reçues** :
- `disposal_found` (from another Red)
  - Lecture : `known_disposal_zone = message.position`

**Phase initiale (disposal discovery)** :
1. Navigue vers colonne Est (x = width - 2)
2. Déplacement vertical aléatoire jusqu'à découverte radioactivity=10
3. Premier Red découvrant → broadcast `disposal_found`
4. Autres Reds reçoivent et mettent à jour `known_disposal_zone`

**Direct Handoff Mode** (obligatoire si carrying ANY waste) :
- Destination unique : `known_disposal_zone`
- Pas de dépôt intermédiaire (sauf timeout forcé)
- Drop at disposal → waste removed, `disposed_counts[color]` incremented

**Coordination implicite** :
- Reds se concurrencent pour déchets au sol (first-arrival pickup)
- Pas de query/response ; seulement perception + action autonome

**Picking up green/yellow at frontier** :
- Possible UNIQUEMENT à frontière Z2/Z3
- Rare (only if Yellow/Green drop there)
- Red absorbs → direct transport to disposal

**Priorités délibération** :
1. Discover disposal (if not known)
2. Send message (si pending)
3. Resolve assigned waste (if assignation protocol extends to Red in future)
4. Direct transport to disposal (if carrying)
5. Pickup waste (if available & at frontier or zone-interior for red)
6. Navigate to known waste targets
7. Explore frontier/patrol Z3

---

## 6. Identificateurs

**Chaque robot** a un `agent_id` unique (incrémenté à création) :
- Green_1, Green_2, ... → agent_id = 1, 2, ...
- Yellow_1, Yellow_2, ... → agent_id = 3, 4, ...
- Red_1, Red_2, ... → agent_id = 5, 6, ...

**Chaque déchet** a un `waste_id` unique (incrémenté à création) :
- Déchets initiaux (green, yellow, red créés au démarrage) → waste_id = 1, 2, ...
- Déchets transformés (green→yellow, yellow→red) → new waste_id (ex. waste_id = 10 pour nouveau jaune)

**Chaque query-response pair** a un `query_id` unique :
- Broadcast carry_query → crée query_id unique
- Yellow responses reference ce query_id
- Green stocke responses par query_id dans `id_and_position_carrier_response[query_id]`

---

## 7. Observabilité Simulation (UI)

**Étiquette des déchets** :
- `waste_id [A<agent_id>]` quand owner assigne est connu
- Exemple : `10 [A3]` = waste_id 10 assigné à agent 3 (Yellow_1)

**Étiquette des robots** :
- `A<agent_id>` si pas d'assignation en cours
- `A<agent_id> | W<assigned_waste_id>` si assignation active
- Exemple : `A3 | W10` = agent 3 assigné à waste 10

**Historique des messages** (optionnel dans telemetry) :
- `last_message_sent_step` : étape du dernier envoi
- `last_message_sent_count` : nombre de messages envoyés

**Marqueurs de status** :
- Green at border = prêt pour handoff
- Yellow with pending response = en attente
- Red scanning = searching disposal

Ces marqueurs permettent de vérifier visuellement que la communication et assignation post-handoff sont bien matérialisées dans la simulation.

---

## Résumé des Changements / Améliorations

✓ Architecture messaging clarifiée (queue vs exécution)
✓ Tableau complet des performatives avec catégories FIPA
✓ 5 protocoles détaillés avec diagrammes AUML et timelines
✓ Cas dégénérés documentés (non-responses, reordering, etc.)
✓ Priorités délibération par rôle
✓ Contraintes frontière exhaustives
✓ Identificateurs explicites (agent_id, waste_id, query_id)
✓ Observabilité UI pour validation

