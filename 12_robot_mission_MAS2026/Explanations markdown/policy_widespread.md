# Policy Widespread

## 1. General Principle
- This policy keeps the same local decision structure as the no-communication version, but enables explicit messaging.
- Messages are processed automatically at the beginning of each step.
- Sending a message is an atomic action: if an agent sends, no other action is executed on that turn.

## 2. Message Set
- `carry_query_empty` and `carry_query_not_empty`: Green asks Yellow to take charge of a waste delivery.
- `carry_response`: Yellow accepts the delivery request.
- `delivery_details`: Green assigns a specific waste to a selected Yellow.
- `lock_delivery`: Green broadcasts a lock to avoid duplicated pickups.
- `waste_presence`: fallback broadcast when Green receives no response.
- `disposal_found`: Red broadcasts the disposal zone position to the other Reds.

## 3. Common Rules
- Zone restrictions, collision avoidance, `_move_toward()`, and timeout handling are the same as in the no-communication policy.
- The communication layer only changes the delivery/coordination part of the decision tree.

## 4. Role Behaviour

### 4.1 Green
- Green still prioritizes timeout handling and then delivery toward the eastern border of Z1.
- When carrying yellow, Green uses the query-response protocol to ask Yellows for a handoff.
- Green stores responses by `query_id`, selects the closest responder, sends `delivery_details`, and broadcasts `lock_delivery`.
- If no responder is available, Green falls back to `waste_presence`.
- Green does not use smart exploration sharing in this policy.

### 4.2 Yellow
- Yellow can answer `carry_query_empty` or `carry_query_not_empty` only when its current inventory and assignment state allow it.
- If a delivery is assigned, Yellow resolves the assigned waste first.
- Yellow then handles timeout, transformation, pickup, movement, and exploration.
- Yellow can receive `delivery_details` and `lock_delivery` to update its assignment state.
- Yellow can also receive `disposal_found` from Red.

### 4.3 Red
- Red discovers the disposal zone and broadcasts `disposal_found` once it is known.
- If Red carries any waste, it moves directly to the disposal zone and drops it.
- Otherwise it can answer delivery-related messages, resolve assignments, pickup waste, and explore.

## 5. Identifiers
- Each agent has a unique `agent_id`.
- Each waste has a unique `waste_id`.
- Each delivery negotiation is tracked by `query_id`.

## 6. UI Notes
- Message coordination is visible through the mailbox state and assigned waste labels.
