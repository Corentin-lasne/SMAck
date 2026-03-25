""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent
from config import actions
from objects import wasteAgent
from collections import deque
import random

# Utility functions for pathfinding and movement

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors_4(pos):
    x, y = pos
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

class baseAgent(Agent):
    """ 
    Base class for all robot agents.
    """

    target_waste_type = None
    result_waste_type = None
    allowed_zones = []
    max_capacity = 2

    def __init__(self, model, agent_id=None):
        super().__init__(model)
        self.agent_id = agent_id
        self.percepts = {}
        self.inventory = []
        self.carry_steps = 0
        self.direct_handoff_mode = False

        self.known_map = {}
        self.waste_map = {}
        self.visited = set()
        self.target_pos = None
        self.scout_target = None  # Persistent target for patrolling/scouting

    def step(self):
        self.step_agent()

    def step_agent(self):
        self.percepts = self.model.get_percepts(self)
        self.update(self.percepts)
        if self.inventory:
            self.carry_steps += 1
        else:
            self.carry_steps = 0
            self.direct_handoff_mode = False
        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.update(new_percepts)

    def _carry_step_limit(self):
        """Return carry timeout in number of steps, based on grid size."""
        return (self.model.grid.width + self.model.grid.height)/2

    def can_pick_waste_type(self, waste_type):
        """Return True when this agent can pick the given waste type."""
        return waste_type == self.target_waste_type

    def can_add_waste_type(self, waste_type):
        """Apply carrying constraints before allowing a pickup."""
        if not self.can_pick_waste_type(waste_type):
            return False
        if len(self.inventory) >= self.max_capacity:
            return False
        if not self.inventory:
            return True

        # If carrying a non-native waste, this must remain the only carried item.
        if any(w.waste_type != self.target_waste_type for w in self.inventory):
            return False

        # Non-native waste can only be carried alone.
        if waste_type != self.target_waste_type:
            return False

        return True

    def _eastern_border_x(self):
        """Return the easternmost x-column allowed for this agent."""
        zone_bounds = {
            "z1": self.model.z1,
            "z2": self.model.z2,
            "z3": self.model.z3,
        }
        right_cols = [zone_bounds[z][2] - 1 for z in self.allowed_zones if z in zone_bounds]
        return max(right_cols)

    def _timeout_drop_action(self):
        """If carrying for too long, force move to eastern border then drop."""
        if not self.inventory:
            return None
        if self.carry_steps < self._carry_step_limit():
            return None

        target_x = self._eastern_border_x()
        if self.pos[0] == target_x:
            return "drop"
        action = self._move_toward((target_x, self.pos[1]))
        return action or self._explore_action()

    def _known_targets_on_frontier(self, waste_type, frontier_x):
        """Return known positions of given waste type located on frontier column."""
        return [
            p for p, wt in self.waste_map.items()
            if wt == waste_type and p[0] == frontier_x and self.model.is_position_allowed(self, p)
        ]

    def update(self, percepts):
        surrounding = percepts.get("surrounding", {})
        for pos, contents in surrounding.items():
            type_list = [type(obj).__name__ for obj in contents]
            self.known_map[pos] = type_list
 
            # Update waste map
            waste_here = [obj for obj in contents if isinstance(obj, wasteAgent)]
            if waste_here:
                # Keep only the first waste type found (cells have at most one waste)
                self.waste_map[pos] = waste_here[0].waste_type
            else:
                # No waste seen here → remove from waste map if present
                self.waste_map.pop(pos, None)
 
        # Mark current cell as visited
        if self.pos:
            self.visited.add(self.pos)

    def _safe_move_actions(self, latest_observation):
        """Return movement actions that do not lead to a cell occupied by another robot."""
        if not self.pos:
            return []
        x, y = self.pos
        surrounding = latest_observation.get("surrounding", {})
        target_by_action = {
            "move_up": (x, y + 1),
            "move_down": (x, y - 1),
            "move_right": (x + 1, y),
            "move_left": (x - 1, y),
        }
        safe_actions = []
        for action_name, target_pos in target_by_action.items():
            if target_pos not in surrounding:
                continue
            target_contents = surrounding[target_pos]
            if any(isinstance(obj, baseAgent) and obj is not self for obj in target_contents):
                continue  # blocked by another robot
            if not self.model.is_position_allowed(self, target_pos):
                continue
            safe_actions.append((action_name, target_pos))
        return safe_actions
    
    def _move_toward(self, target):
        """
        Return the best *safe* action to get closer to *target*.
        Uses BFS for short-term pathfinding around obstacles, falls back to greedy.
        """
        start = self.pos
        if start == target:
            return None
 
        safe_first_steps_actions = self._safe_move_actions(self.percepts)
        safe_first_steps = {tpos: act for act, tpos in safe_first_steps_actions}
 
        # BFS — find shortest path in known map
        queue = deque([(start, [])])
        seen  = {start}
        
        # Limit BFS depth to prevent hanging if target is unreachable
        max_depth = 50 
        
        while queue:
            pos, path = queue.popleft()
            if len(path) > max_depth:
                break

            if pos == target:
                if path:
                    first_step = path[0]
                    if first_step in safe_first_steps:
                        return safe_first_steps[first_step]
                break

            for npos in neighbors_4(pos):
                if npos in seen:
                    continue
                # For pathfinding, we only care if the cell is traversable (allowed zone)
                if not self.model.is_position_allowed(self, npos):
                    continue
                
                seen.add(npos)
                new_path = path + [npos]
                queue.append((npos, new_path))
 
        # Fallback: Greedy move towards target among safe actions
        if not safe_first_steps_actions:
            return None
            
        # Add some randomness to break symmetric deadlocks (face-to-face)
        safe_sorted = sorted(
            safe_first_steps_actions,
            key=lambda a: manhattan(a[1], target) + random.uniform(0, 0.5)
        )
        return safe_sorted[0][0]

    def _explore_action(self):
        """
        Move toward the nearest frontier cell or random safe move.
        """
        frontier = []
        # Optimization: only check a subset of known map if it gets too large
        for pos in self.known_map:
            if not self.model.is_position_allowed(self, pos):
                continue
            for npos in neighbors_4(pos):
                if npos not in self.known_map and self.model.is_position_allowed(self, npos):
                    frontier.append(pos)
                    break
 
        if frontier:
            # Pick closest frontier
            target = min(
                frontier,
                key=lambda p: manhattan(self.pos, p) + random.uniform(0, 0.5)
            )
            action = self._move_toward(target)
            if action:
                return action
 
        # Random walk if no frontier found or unreachable
        safe = self._safe_move_actions(self.percepts)
        if safe:
            return random.choice(safe)[0]
        return None

    def deliberate(self, knowledge=None):
        raise NotImplementedError("This method should be implemented by subclasses")

class greenAgent(baseAgent):

    allowed_zones = ["z1"]
    target_waste_type = "green"
    result_waste_type = "yellow"
    max_capacity = 2

    def can_add_waste_type(self, waste_type):
        if waste_type != "green":
            return False
        if len(self.inventory) >= self.max_capacity:
            return False

        border_x = self.model.z1[2] - 1
        # Green agent cannot pick a green at Z1/Z2 frontier when empty.
        if self.pos[0] == border_x and len(self.inventory) == 0:
            return False
        return True

    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]

        timeout_action = self._timeout_drop_action()
        if timeout_action:
            return timeout_action

        # Green direct handoff is only for transformed yellow.
        if "yellow" in inv_types:
            self.direct_handoff_mode = True
            target_x = self.model.z1[2] - 1
            if self.pos[0] == target_x:
                return "drop"
            action = self._move_toward((target_x, self.pos[1]))
            return action or self._explore_action()
        self.direct_handoff_mode = False
        
        # 1. Transform if full of green
        if inv_types.count("green") >= 2:
            return "transform"

        # 3. Pick up green waste if here
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and self.can_add_waste_type(o.waste_type) for o in current_contents):
            return "pick_up"

        # 4. Move to known green waste
        border_x = self.model.z1[2] - 1
        green_targets = [
            p for p, wt in self.waste_map.items()
            if wt == "green"
            and self.model.is_position_allowed(self, p)
            and not (p[0] == border_x and len(self.inventory) == 0)
        ]
        if green_targets:
            closest = min(green_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        return self._explore_action()

class yellowAgent(baseAgent):
 
    target_waste_type = "yellow"
    result_waste_type = "red"
    allowed_zones = ["z1", "z2"]
    max_capacity = 2

    def can_add_waste_type(self, waste_type):
        if len(self.inventory) >= self.max_capacity:
            return False

        left_border_x = self.model.z1[2] - 1
        right_border_x = self.model.z2[2] - 1
        inv_types = [w.waste_type for w in self.inventory]

        if waste_type == "green":
            # Yellow can carry green only from Z1/Z2 frontier, and only with empty inventory.
            return self.pos[0] == left_border_x and len(self.inventory) == 0

        if waste_type == "yellow":
            # If carrying green, yellow must remain the only item.
            if "green" in inv_types:
                return False
            # At Z2/Z3 frontier, yellow can be picked only if already carrying yellow.
            if self.pos[0] == right_border_x and "yellow" not in inv_types:
                return False
            return True

        # Yellow agent never picks red from the floor.
        return False
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]
        
        timeout_action = self._timeout_drop_action()
        if timeout_action:
            return timeout_action

        frontier_x = self.model.z1[2] - 1
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])

        # Priority pickup on incoming frontier (handoff area).
        if self.pos[0] == frontier_x:
            if any(
                isinstance(o, wasteAgent) and self.can_add_waste_type(o.waste_type)
                for o in current_contents
            ):
                if len(self.inventory) == 0:
                    self.direct_handoff_mode = True
                    return "pick_up"

        # If a frontier waste is known, go to it before normal exploration.
        if not self.inventory:
            frontier_targets = (
                self._known_targets_on_frontier("green", frontier_x)
                + self._known_targets_on_frontier("yellow", frontier_x)
            )
            if frontier_targets:
                closest = min(frontier_targets, key=lambda p: manhattan(self.pos, p))
                action = self._move_toward(closest)
                if action:
                    return action

        # Yellow uses direct handoff only when carrying green: deliver to Z2 east border.
        if any(w == "green" for w in inv_types):
            self.direct_handoff_mode = True
            target_x = self.model.z2[2] - 1
            if self.pos[0] == target_x:
                return "drop"
            action = self._move_toward((target_x, self.pos[1]))
            return action or self._explore_action()
        self.direct_handoff_mode = False
 
        # 1. Transform if full of yellow
        if inv_types.count("yellow") >= 2:
            return "transform"
 
        # 2. Deliver red waste to border of Z2
        if "red" in inv_types:
            target_x = self.model.z2[2] - 1
            if self.pos[0] == target_x:
                return "drop"
            
            target = (target_x, self.pos[1])
            action = self._move_toward(target)
            return action or self._explore_action()
 
        # 3. Pick up yellow/green waste under yellow constraints
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(
            isinstance(o, wasteAgent) and self.can_add_waste_type(o.waste_type)
            for o in current_contents
        ):
            return "pick_up"
 
        # 4. Move to known reachable yellow/green waste
        right_border_x = self.model.z2[2] - 1
        yellow_targets = [
            p for p, wt in self.waste_map.items()
            if (
                (wt == "green" and p[0] == frontier_x and len(self.inventory) == 0)
                or (wt == "yellow" and not (p[0] == right_border_x and "yellow" not in inv_types))
            )
            and self.model.is_position_allowed(self, p)
        ]
        if yellow_targets:
            closest = min(yellow_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
        
        # 5. Scout: Mix between patrolling the drop zone (handoffs) and exploring the zone (initial waste)
        if self.scout_target is None or self.pos == self.scout_target:
            # 50% chance to check the border, 50% chance to explore deep into Z2
            if random.random() < 0.5:
                # Patrol the border (Z1 East Border)
                scout_x = self.model.z1[2] - 1
                current_y = self.pos[1]
                h = self.model.grid.height
                if current_y > h // 2:
                    new_y = random.randint(0, h // 3)
                else:
                    new_y = random.randint(2 * h // 3, h - 1)
                self.scout_target = (scout_x, new_y)
            else:
                # Explore Z2 for initial waste
                # Pick a random point in Z2
                x_min, y_min, x_max, y_max = self.model.z2
                # Ensure we pick a valid x inside Z2 (x_max is exclusive in range, but grid is 0-indexed)
                rand_x = random.randint(x_min, x_max - 1)
                rand_y = random.randint(y_min, y_max - 1)
                self.scout_target = (rand_x, rand_y)
             
        action = self._move_toward(self.scout_target)
        return action or self._explore_action()

class redAgent(baseAgent):
 
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1

    def can_pick_waste_type(self, waste_type):
        return waste_type in {"green", "yellow", "red"}

    def can_add_waste_type(self, waste_type):
        if len(self.inventory) >= self.max_capacity:
            return False

        right_border_x = self.model.z2[2] - 1
        if waste_type in {"green", "yellow"}:
            # Red can pick green/yellow only on Z2/Z3 frontier.
            return self.pos[0] == right_border_x
        if waste_type == "red":
            return True
        return False
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]

        # Red direct-handoff mode is mandatory for any carried waste.
        if self.inventory:
            self.direct_handoff_mode = True
            target = self.model.waste_disposal_zone
            if self.pos == target:
                return "drop"
            action = self._move_toward(target)
            return action or self._explore_action()
        self.direct_handoff_mode = False

        frontier_x = self.model.z2[2] - 1
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        
        # Priority pickup on incoming frontier, then direct transport to disposal.
        if self.pos[0] == frontier_x:
            if any(
                isinstance(o, wasteAgent) and self.can_add_waste_type(o.waste_type)
                for o in current_contents
            ):
                if len(self.inventory) == 0 :
                    self.direct_handoff_mode = True
                    return "pick_up"

        if not self.inventory:
            frontier_targets = (
                self._known_targets_on_frontier("red", frontier_x)
                + self._known_targets_on_frontier("yellow", frontier_x)
                + self._known_targets_on_frontier("green", frontier_x)
            )
            if frontier_targets:
                closest = min(frontier_targets, key=lambda p: manhattan(self.pos, p))
                action = self._move_toward(closest)
                if action:
                    return action
 
        # 2. Pick up red waste if here
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(
            isinstance(o, wasteAgent) and self.can_add_waste_type(o.waste_type)
            for o in current_contents
        ):
            return "pick_up"
        
        # 3. Move to known reachable waste (red anywhere, green/yellow on Z2/Z3 frontier only)
        red_targets = [
            p for p, wt in self.waste_map.items()
            if (
                wt == "red"
                or (wt in {"green", "yellow"} and p[0] == frontier_x)
            )
            and self.model.is_position_allowed(self, p)
        ]
        if red_targets:
            closest = min(red_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
            
        # 4. Scout: Mix between patrolling the drop zone (handoffs) and exploring the zone (initial waste)
        if self.scout_target is None or self.pos == self.scout_target:
            # 50% chance to check the border, 50% chance to explore deep into Z3
            if random.random() < 0.5:
                # Patrol the border (Z2 East Border)
                scout_x = self.model.z2[2] - 1
                current_y = self.pos[1]
                h = self.model.grid.height
                if current_y > h // 2:
                    new_y = random.randint(0, h // 3)
                else:
                    new_y = random.randint(2 * h // 3, h - 1)
                self.scout_target = (scout_x, new_y)
            else:
                # Explore Z3 for initial waste
                x_min, y_min, x_max, y_max = self.model.z3
                rand_x = random.randint(x_min, x_max - 1)
                rand_y = random.randint(y_min, y_max - 1)
                self.scout_target = (rand_x, rand_y)
             
        action = self._move_toward(self.scout_target)
        return action or self._explore_action()