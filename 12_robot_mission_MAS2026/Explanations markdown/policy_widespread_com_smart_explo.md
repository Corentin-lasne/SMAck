# Policy Widespread with Smart Exploration

## 1. General Principle
- This policy is the same as `widespread`, but smart exploration sharing is enabled.
- The code currently calls the exploration-sharing helper with an interval of 30 steps.
- The model parameter `exploration_share_interval_steps` exists in the UI and runner, but the current policy implementation uses the fixed value 30 inside the policy functions.

## 2. Message Set
- The same message set as `widespread` is available.
- The extra behaviour is the periodic sharing of explored positions between same-colour agents through `exploration_positions_share`.

## 3. Common Rules
- All movement, timeout, pickup, transformation, and delivery rules remain the same as in `widespread`.
- Smart exploration does not replace delivery coordination; it is evaluated after the higher-priority delivery actions.

## 4. Role Behaviour

### 4.1 Green
- Green follows the same query-response delivery logic as in `widespread`.
- After delivery priorities, it may share explored positions if the interval condition is met.

### 4.2 Yellow
- Yellow follows the same delivery and assignment handling as in `widespread`.
- Smart exploration sharing is checked after timeout and delivery resolution, and before transformation / movement / exploration.

### 4.3 Red
- Red keeps the same disposal discovery and delivery logic as in `widespread`.
- After the delivery priorities, Red may share explored positions when the interval condition is met.

## 5. What Changes Compared to Widespread
- `smart_exploration_enabled = True` for all colors.
- Same communication protocol, but with periodic sharing of explored positions.
- This makes the policy more coordinated, at the cost of extra communication overhead.

## 6. Identifiers
- Each agent has a unique `agent_id`.
- Each waste has a unique `waste_id`.
- Each negotiation still uses `query_id` where relevant.
