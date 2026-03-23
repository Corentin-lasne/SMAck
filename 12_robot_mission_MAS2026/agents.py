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

    def __init__(self, model):
        super().__init__(model)
        self.percepts = {}
        self.inventory = []

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
        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.update(new_percepts)

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

    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]
        
        # 1. Transform if full of green
        if inv_types.count("green") >= 2:
            return "transform"

        # 2. Deliver yellow waste to border of Z1
        if "yellow" in inv_types:
            # Target is the easternmost column of Z1
            target_x = self.model.z1[2] - 1
            if self.pos[0] == target_x:
                return "drop"
            
            # Move to any cell in that column
            target = (target_x, self.pos[1])
            action = self._move_toward(target)
            return action or self._explore_action()

        # 3. Pick up green waste if here
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "green" for o in current_contents):
            if len(self.inventory) < self.max_capacity:
                return "pick_up"

        # 4. Move to known green waste
        green_targets = [p for p, wt in self.waste_map.items() 
                         if wt == "green" and self.model.is_position_allowed(self, p)]
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
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]
 
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
 
        # 3. Pick up yellow waste if here
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "yellow" for o in current_contents):
            if len(self.inventory) < self.max_capacity:
                return "pick_up"
 
        # 4. Move to known yellow waste
        yellow_targets = [p for p, wt in self.waste_map.items()
                          if wt == "yellow" and self.model.is_position_allowed(self, p)]
        if yellow_targets:
            closest = min(yellow_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
        
        # 5. Scout the Green Drop Zone (Z1 East Border) for new yellow waste
        scout_x = self.model.z1[2] - 1
        
        # Persistent Patrol Logic:
        # If no target, or we reached it, pick a new one at the opposite vertical end
        # This forces the agent to traverse the full height of the drop zone
        if self.scout_target is None or self.pos == self.scout_target:
             current_y = self.pos[1]
             h = self.model.grid.height
             
             # If generally in the top half, go to bottom third.
             # If generally in bottom half, go to top third.
             if current_y > h // 2:
                 new_y = random.randint(0, h // 3)
             else:
                 new_y = random.randint(2 * h // 3, h - 1)
                 
             self.scout_target = (scout_x, new_y)
             
        action = self._move_toward(self.scout_target)
        return action or self._explore_action()

class redAgent(baseAgent):
 
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]
 
        # 1. Deliver red waste to Disposal Zone
        if "red" in inv_types:
            target = self.model.waste_disposal_zone
            if self.pos == target:
                return "drop"
            action = self._move_toward(target)
            return action or self._explore_action()
 
        # 2. Pick up red waste if here
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "red" for o in current_contents):
            if len(self.inventory) < self.max_capacity:
                return "pick_up"
        
        # 3. Move to known red waste
        red_targets = [p for p, wt in self.waste_map.items()
                       if wt == "red" and self.model.is_position_allowed(self, p)]
        if red_targets:
            closest = min(red_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
            
        # 4. Scout the Yellow Drop Zone (Z2 East Border)
        scout_x = self.model.z2[2] - 1
        
        # Persistent Patrol Logic (same as Yellow)
        if self.scout_target is None or self.pos == self.scout_target:
             current_y = self.pos[1]
             h = self.model.grid.height
             if current_y > h // 2:
                 new_y = random.randint(0, h // 3)
             else:
                 new_y = random.randint(2 * h // 3, h - 1)
             self.scout_target = (scout_x, new_y)
             
        action = self._move_toward(self.scout_target)
        return action or self._explore_action()