# Robot Mission Policy Documentation (Step 1: No Communication)

## 1. Objective
The goal of Step 1 was to design autonomous policies for a multi-agent system where robots (Green, Yellow, Red) must collaborate to transform and transport waste across three radioactive zones. The key constraint is the **absence of direct communication** between agents. Collaboration must emerge solely through environmental interaction ("stigmergy").

## 2. Initial Approach & Challenges
Our initial implementation relied on simple reactive behaviors: agents would look at their immediate surroundings and act. However, we observed several critical failure modes:

*   **The "Dithering" Problem**: Without memory or persistent goals, agents would step towards a destination, get blocked or see a new stimulus, and change their mind immediately. This resulted in agents "vibrating" in place or moving back and forth inefficiently.
*   **The Handoff Bottleneck**: Green agents drop waste at the border of Zone 1, but Yellow agents (operating in Zone 2) would just wander randomly. The probability of a Yellow agent stumbling upon the specific cell where a Green agent dropped waste was too low to verify efficient throughput.
*   **Border Clustering vs. Deep Exploration**: Once we optimized agents to check the borders for handoffs, they tended to *stay* there. This meant that initial waste located deep inside Zone 2 or Zone 3 was completely ignored because agents were too busy patrolling the handoff lines.

## 3. Solution Evolution

To address these challenges, we evolved the agent architecture through several iterations:

### A. Memory & Mapping
We endowed agents with a `known_map`. While they cannot communicate, they *can* remember what they have seen. If an agent sees a waste item but cannot pick it up (e.g., inventory full), it remembers the location. Later, when empty, it can return directly to that location instead of searching randomly.

### B. Persistent Patrols (Solving "Dithering")
To fix the movement instability, we implemented **Persistence**. When an agent decides to "scout" a border or move to a target, it commits to that target until it arrives (or the target becomes invalid).
*   *Specific Tactic*: For patrolling the handoff borders, agents pick a target at the *opposite end* of the border (e.g., if at the top, go to the bottom). This forces them to sweep the entire length of the active zone, maximizing the chance of finding dropped waste.

### C. Hybrid Scout/Explore Strategy (Solving "Deep Waste")
To balance the need for checking handoffs (high priority for flow) vs. collecting initial waste (high priority for completion), we implemented a probabilistic behavior for Yellow and Red agents when they have no active target:
*   **50% Handoff Patrol**: Go to the border of the previous zone to look for dropped waste.
*   **50% Deep Exploration**: Pick a random coordinate deep inside their own zone and travel there. This ensures agents periodically break away from the borders to clean up the rest of the map.

## 4. Final Policy Logic

### Priority Hierarchy
Every agent follows a strict priority queue in its `deliberate()` cycle. The first applicable condition triggers the action.

#### 🟢 Green Agent (Zone 1)
1.  **Transform**: If carrying 2 Green wastes → `transform` (to Yellow).
2.  **Deliver**: If carrying Yellow waste → Move to East Border of Z1. If at border → `drop`.
3.  **Collect**: If standing on Green waste → `pick_up`.
4.  **Retrieve**: If a Green waste location is in memory → Move towards it.
5.  **Explore**: Random movement or frontier exploration within Z1.

#### 🟡 Yellow Agent (Zone 1 & 2)
1.  **Transform**: If carrying 2 Yellow wastes → `transform` (to Red).
2.  **Deliver**: If carrying Red waste → Move to East Border of Z2. If at border → `drop`.
3.  **Collect**: If standing on Yellow waste → `pick_up`.
4.  **Retrieve**: If a Yellow waste location is in memory → Move towards it.
5.  **Scout/Patrol**:
    *   *Coin Flip (50%)*: Move to Z1 East Border (Green's drop zone) and sweep vertically.
    *   *Coin Flip (50%)*: Move to a random point deep in Z2.

#### 🔴 Red Agent (All Zones)
1.  **Deliver**: If carrying Red waste → Move to Disposal Zone (Radioactivity 4). If there → `drop`.
2.  **Collect**: If standing on Red waste → `pick_up`.
3.  **Retrieve**: If a Red waste location is in memory → Move towards it.
4.  **Scout/Patrol**:
    *   *Coin Flip (50%)*: Move to Z2 East Border (Yellow's drop zone) and sweep vertically.
    *   *Coin Flip (50%)*: Move to a random point deep in Z3.

## 5. Movement Primitives
*   **`_move_toward(target)`**: Uses Breadth-First Search (BFS) for short-range local pathfinding to avoid obstacles (other robots), falling back to greedy movement for long distances.
*   **`_safe_move_actions`**: Filters out moves that would result in immediate collisions with other robots.
