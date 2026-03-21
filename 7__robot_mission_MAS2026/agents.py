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
from objects import wasteAgent, radioactivityAgent

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
    resulted_waste_type = None
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
        surrounding = self.percepts.get("surrounding", {})
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
        Return the best action to get closer to *target* using BFS on known_map,
        falling back to greedy Manhattan if no path is known.
        """
        # BFS through known positions
        start = self.pos
        if start == target:
            return None
 
        queue = deque([(start, [])])
        seen  = {start}
        while queue:
            pos, path = queue.popleft()
            for npos in neighbors_4(pos):
                if npos in seen:
                    continue
                if not self.model.is_position_allowed(self, npos):
                    continue
                if npos not in self.known_map and npos != target:
                    continue
                seen.add(npos)
                new_path = path + [npos]
                if npos == target:
                    # Return action toward first step
                    next_pos = new_path[0]
                    return self._action_for_step(start, next_pos)
                queue.append((npos, new_path))
 
        # Fallback: greedy among safe moves
        safe = self._safe_move_actions(self.percepts)
        if not safe:
            return None
        best = min(safe, key=lambda a: manhattan(a[1], target))
        return best[0]
 
    def _action_for_step(self, frm, to):
        dx = to[0] - frm[0]
        dy = to[1] - frm[1]
        if dx == 1:  return "move_right"
        if dx == -1: return "move_left"
        if dy == 1:  return "move_up"
        if dy == -1: return "move_down"
        return None
 
    def _explore_action(self):
        """
        Move toward the nearest unvisited cell reachable within the agent's zones.
        """
        # Collect frontier: known cells adjacent to unknown cells
        frontier = []
        for pos in self.known_map:
            if not self.model.is_position_allowed(self, pos):
                continue
            for npos in neighbors_4(pos):
                if npos not in self.known_map and self.model.is_position_allowed(self, npos):
                    frontier.append(pos)
                    break
 
        if frontier:
            target = min(frontier, key=lambda p: manhattan(self.pos, p))
            action = self._move_toward(target)
            if action:
                return action
 
        # Last resort: random safe move
        safe = self._safe_moves()
        if safe:
            return self.random.choice(safe)[0]
        return "move_right"

    def deliberate(self, knowledge):
        raise NotImplementedError("This method should be implemented by subclasses")

class greenAgent(baseAgent):

    allowed_zones = ["z1"]
    target_waste_type = "green"
    resulted_waste_type = "yellow"
    max_capacity = 2

    def deliberate(self):
        inv = self.inventory
        inv_types = [w.waste_type for w in inv]
 
        # Transform into yellow waste
        if inv_types.count("green") == 2:
            return "transform"
 
        # Go east to drop the yellow waste
        if "yellow" in inv_types:
            east_x = self.model.z1[2] - 1   
            if self.pos[0] == east_x:
                return "drop"
            action = self._move_toward((east_x, self.pos[1]))
            return action or self._explore_action()
 
        # Pick up green waste if on it and not full
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "green" for o in current_contents):
            if len(inv) < self.max_capacity:
                return "pick_up"
 
        # Go toward closest green waste in known map
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
        inv = self.inventory
        inv_types = [w.waste_type for w in inv]
 
        if inv_types.count("yellow") == 2:
            return "transform"
 
        if "red" in inv_types:
            east_x = self.model.z2[2] - 1
            if self.pos[0] == east_x:
                return "drop"
            action = self._move_toward((east_x, self.pos[1]))
            return action or self._explore_action()
 
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "yellow" for o in current_contents):
            if len(inv) < self.max_capacity:
                return "pick_up"
 
        yellow_targets = [p for p, wt in self.waste_map.items()
                          if wt == "yellow" and self.model.is_position_allowed(self, p)]
        if yellow_targets:
            closest = min(yellow_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
 
        return self._explore_action()

class redAgent(baseAgent):
    """
    All zones (z1, z2, z3).
    - Picks up 1 red waste.
    - Brings it to the waste disposal zone (radioactivityAgent level 4).
    """
 
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1
 
    def _find_disposal_zone(self):
        """Return the disposal zone position from known_map (radioactivity level 4)."""
        for pos, _ in self.known_map.items():
            cell = self.model.grid.get_cell_list_contents([pos])
            for obj in cell:
                if isinstance(obj, radioactivityAgent) and obj.radioactivity == 4:
                    return pos
        return None
 
    def deliberate(self):
        inv = self.inventory
        inv_types = [w.waste_type for w in inv]
 
        if "red" in inv_types:
            disposal = self._find_disposal_zone()
            if disposal:
                if self.pos == disposal:
                    return "drop"
                action = self._move_toward(disposal)
                return action or self._explore_action()
            else:
                # Disposal not yet seen → explore eastward
                return self._explore_action()
 
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "red" for o in current_contents):
            return "pick_up"

        red_targets = [p for p, wt in self.waste_map.items() if wt == "red"]
        if red_targets:
            closest = min(red_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()
 
        return self._explore_action()
