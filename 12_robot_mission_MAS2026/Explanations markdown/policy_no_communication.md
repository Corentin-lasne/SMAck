# Policy No Communication

## 1. General Principle
- No messages are exchanged between agents.
- Coordination is purely local and environmental: agents use their own perception, local memory, and waste deposits on the grid.

## 2. Common Rules
- Each agent moves only inside its authorized zones.
- Robot-robot collisions are avoided by `_safe_move_actions()`.
- Navigation uses `_move_toward()`, then exploration if the target is unreachable.
- If an agent carries waste for too long, the timeout logic forces a move to the eastern border and then a drop.
- If no legal action exists, the model treats the turn as a no-op.

## 3. Role Behaviour

### 3.1 Green
- Timeout has the highest priority.
- If one yellow is already in inventory, Green moves to the eastern border of Z1 and drops it.
- If two green wastes are in inventory, Green transforms them into one yellow.
- Green then picks up green waste, moves toward known green targets, or explores.

### 3.2 Yellow
- Timeout has the highest priority.
- If Yellow carries green or red waste, it moves to the eastern border and drops it.
- If two yellow wastes are in inventory, Yellow transforms them into one red.
- Yellow then picks up yellow waste, moves toward known yellow targets, or explores in Z2.

### 3.3 Red
- Red first discovers the disposal zone if it is still unknown.
- If Red carries any waste, it moves directly toward the known disposal zone and drops it there.
- Otherwise it picks up waste when possible, moves toward known targets, or explores in Z3.

## 4. Identifiers
- Each robot has a unique `agent_id`.
- Each waste has a unique `waste_id`.

## 5. UI Notes
- Waste labels may show assignment information when known.
- Robot labels show the current agent id and, if relevant, the assigned waste id.
