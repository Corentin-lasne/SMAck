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
        self.border_drop_signals = {}
        self.pending_help_targets = []
        self.disposal_hint = None

    def step(self):
        self.step_agent()

    def step_agent(self):
        self.percepts = self.model.get_percepts(self)
        self.update(self.percepts)
        self._process_messages()
        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.update(new_percepts)

    def _process_messages(self):
        messages = self.model.get_messages(self)
        for msg in messages:
            topic = msg.get("topic")
            if topic == "border_drop":
                drop_type = msg.get("waste_type")
                drop_pos = msg.get("position")
                if drop_type and drop_pos:
                    self.border_drop_signals[drop_type] = drop_pos
            elif topic == "pair_help":
                sender_id = msg.get("sender_id")
                position = msg.get("position")
                waste_type = msg.get("waste_type")
                if sender_id is not None and position and waste_type:
                    self.pending_help_targets.append(
                        {
                            "sender_id": sender_id,
                            "position": position,
                            "waste_type": waste_type,
                        }
                    )
            elif topic == "disposal_found":
                position = msg.get("position")
                if position:
                    self.disposal_hint = position

    def send_team_message(self, team_name, topic, payload):
        self.model.send_message(self, team_name, topic, payload)

    def _zone_west_anchor(self):
        if not self.allowed_zones:
            return self.pos
        zone_name = self.allowed_zones[0]
        zone = getattr(self.model, zone_name, None)
        if zone is None:
            return self.pos
        x = zone[0]
        y = self.pos[1] if self.pos else zone[1]
        y = max(zone[1], min(zone[3] - 1, y))
        return (x, y)

    def _zone_east_anchor(self):
        if not self.allowed_zones:
            return self.pos
        zone_name = self.allowed_zones[-1]
        zone = getattr(self.model, zone_name, None)
        if zone is None:
            return self.pos
        x = zone[2] - 1
        y = self.pos[1] if self.pos else zone[1]
        y = max(zone[1], min(zone[3] - 1, y))
        return (x, y)

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
        Return the best *safe* action to get closer to *target*.
 
        Strategy:
        1. BFS on known_map; only the first step must be currently free.
        2. If BFS path has a blocked first step, fall through to greedy.
        3. Greedy fallback among safe moves with Manhattan + small random jitter
           to break the symmetry that causes face-to-face deadlocks.
        """
        from collections import deque
 
        start = self.pos
        if start == target:
            return None
 
        safe_first_steps = {tpos for _, tpos in self._safe_move_actions(self.percepts)}
 
        # BFS — only the very first step must be currently free
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
                    first = new_path[0]
                    if first in safe_first_steps:
                        return self._action_for_step(start, first)
                    break  # path found but first step blocked → greedy fallback
                queue.append((npos, new_path))
 
        # Greedy fallback with jitter to break ties / deadlocks
        safe = self._safe_move_actions(self.percepts)
        if not safe:
            return None
        safe_sorted = sorted(
            safe,
            key=lambda a: manhattan(a[1], target) + self.random.random() * 0.5
        )
        return safe_sorted[0][0]
 
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
        Move toward the nearest frontier cell (known cell bordering an unknown one).
        Falls back to a random safe move to escape deadlocks.
        """
        frontier = []
        for pos in self.known_map:
            if not self.model.is_position_allowed(self, pos):
                continue
            for npos in neighbors_4(pos):
                if npos not in self.known_map and self.model.is_position_allowed(self, npos):
                    frontier.append(pos)
                    break
 
        if frontier:
            # Jitter breaks ties between equidistant frontier cells
            target = min(
                frontier,
                key=lambda p: manhattan(self.pos, p) + self.random.random() * 0.5
            )
            action = self._move_toward(target)
            if action:
                return action
 
        # No frontier or all paths blocked → random safe move to escape
        safe = self._safe_move_actions(self.percepts)
        if safe:
            return self.random.choice(safe)[0]
        return "move_up"

    def deliberate(self, knowledge):
        raise NotImplementedError("This method should be implemented by subclasses")

class greenAgent(baseAgent):

    allowed_zones = ["z1"]
    target_waste_type = "green"
    result_waste_type = "yellow"
    max_capacity = 2

    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]
 
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
            if len(self.inventory) < self.max_capacity:
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

    def _west_boundary_x(self):
        return self.model.z2[0]

    def _handle_pair_help(self):
        inv_types = [w.waste_type for w in self.inventory]
        if inv_types.count("yellow") != 1:
            return None

        valid = [
            req for req in self.pending_help_targets
            if req["sender_id"] != self.unique_id and req["waste_type"] == "yellow"
        ]
        if not valid:
            return None

        target = min(valid, key=lambda req: manhattan(self.pos, req["position"]))
        if self.pos == target["position"]:
            return "drop"
        return self._move_toward(target["position"])

    def _ask_pair_help(self):
        self.send_team_message(
            "yellowAgent",
            "pair_help",
            {"position": self.pos, "waste_type": "yellow"},
        )

    def _zone_west_patrol(self):
        west_x = self._west_boundary_x()
        y_candidates = [
            max(self.model.z2[1], self.pos[1] - 1),
            self.pos[1],
            min(self.model.z2[3] - 1, self.pos[1] + 1),
        ]
        target = (west_x, self.random.choice(y_candidates))
        action = self._move_toward(target)
        return action or self._explore_action()
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]

        helper_action = self._handle_pair_help()
        if helper_action:
            return helper_action
 
        if inv_types.count("yellow") == 2:
            return "transform"
 
        if "red" in inv_types:
            east_x = self.model.z2[2] - 1
            if self.pos[0] == east_x:
                return "drop"
            action = self._move_toward((east_x, self.pos[1]))
            return action or self._explore_action()

        border_drop = self.border_drop_signals.get("yellow")
        if border_drop and self.model.is_position_allowed(self, border_drop):
            if self.pos == border_drop:
                current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
                if any(isinstance(o, wasteAgent) and o.waste_type == "yellow" for o in current_contents):
                    return "pick_up"
            action = self._move_toward(border_drop)
            if action:
                return action
 
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "yellow" for o in current_contents):
            if len(self.inventory) < self.max_capacity:
                return "pick_up"
 
        yellow_targets = [p for p, wt in self.waste_map.items()
                          if wt == "yellow" and self.model.is_position_allowed(self, p)]
        if yellow_targets:
            closest = min(yellow_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        if inv_types.count("yellow") == 1:
            self._ask_pair_help()
            return self._zone_west_patrol()
 
        return self._zone_west_patrol()

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

    def __init__(self, model):
        super().__init__(model)
        self.disposal_pos = None
        self.scan_direction = 1
 
    def _find_disposal_zone(self):
        """Return the disposal zone position from known_map (radioactivity level 4)."""
        for pos, _ in self.known_map.items():
            cell = self.model.grid.get_cell_list_contents([pos])
            for obj in cell:
                if isinstance(obj, radioactivityAgent) and obj.radioactivity >= 5:
                    return pos
        return None

    def _eastern_scan_action(self):
        east_x = self.model.grid.width - 1
        if self.pos[0] < east_x:
            action = self._move_toward((east_x, self.pos[1]))
            return action or self._explore_action()

        top_y = self.model.grid.height - 1
        bottom_y = 0
        target_y = top_y if self.scan_direction > 0 else bottom_y
        if self.pos[1] == target_y:
            self.scan_direction *= -1
            target_y = top_y if self.scan_direction > 0 else bottom_y

        action = self._move_toward((east_x, target_y))
        return action or self._explore_action()

    def _west_frontier_patrol(self):
        west_x = self.model.z3[0]
        y_candidates = [
            max(self.model.z3[1], self.pos[1] - 1),
            self.pos[1],
            min(self.model.z3[3] - 1, self.pos[1] + 1),
        ]
        target = (west_x, self.random.choice(y_candidates))
        action = self._move_toward(target)
        return action or self._explore_action()
 
    def deliberate(self):
        inv = self.inventory
        inv_types = [w.waste_type for w in inv]

        if self.disposal_hint and self.disposal_pos is None:
            self.disposal_pos = self.disposal_hint

        observed_disposal = self._find_disposal_zone()
        if observed_disposal and self.disposal_pos is None:
            self.disposal_pos = observed_disposal
            self.send_team_message("redAgent", "disposal_found", {"position": observed_disposal})
 
        if "red" in inv_types:
            disposal = self.disposal_pos or observed_disposal
            if disposal:
                if self.pos == disposal:
                    return "drop"
                action = self._move_toward(disposal)
                return action or self._explore_action()
            else:
                return self._eastern_scan_action()
 
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(isinstance(o, wasteAgent) and o.waste_type == "red" for o in current_contents):
            return "pick_up"

        border_drop = self.border_drop_signals.get("red")
        if border_drop and self.model.is_position_allowed(self, border_drop):
            action = self._move_toward(border_drop)
            if action:
                return action

        red_targets = [p for p, wt in self.waste_map.items() if wt == "red"]
        if red_targets:
            closest = min(red_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        if self.disposal_pos is None:
            return self._eastern_scan_action()
 
        return self._west_frontier_patrol()
