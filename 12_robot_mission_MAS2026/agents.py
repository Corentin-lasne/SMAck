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
from objects import wasteAgent, radioactivityAgent
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
        self.current_step = 0
        self.percepts = {}
        self.inventory = []        
        self.carry_steps = 0
        self.direct_handoff_mode = False

        self.known_map = {}
        self.waste_map = {}
        self.waste_id_map = {}
        self.waste_entries_map = {}
        self.visited = set()
        self.target_pos = None
        self.scout_target = None  # Persistent target for patrolling/scouting
        
        self.known_disposal_zone = None
        
        self.pending_messages = []
        self.received_messages = []
        self.locked_waste_ids = set()
        self.assigned_waste_id = None
        self.assigned_waste_pos = None
        self.assigned_requester_id = None  # For carry_query: ID of the green agent requesting pickup
        self.requested_waste_ids = set()
        self.id_and_position_carrier_response = {}

    def step(self):
        self.step_agent()

    def step_agent(self):
        # Message handling is always performed at the beginning of the step.
        self._process_incoming_messages()
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
        self.current_step += 1

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
        targets = []
        for p, entries in self.waste_entries_map.items():
            if p[0] != frontier_x or not self.model.is_position_allowed(self, p):
                continue
            if any(wt == waste_type and self._is_waste_id_allowed(wid) for wt, wid in entries):
                targets.append(p)
        return targets

    def _is_waste_id_allowed(self, waste_id):
        if self.assigned_waste_id is not None and waste_id == self.assigned_waste_id:
            return True
        return waste_id not in self.locked_waste_ids

    def _can_pick_object(self, obj):
        if not isinstance(obj, wasteAgent):
            return False
        if not self.can_add_waste_type(obj.waste_type):
            return False
        return self._is_waste_id_allowed(getattr(obj, "waste_id", None))

    def update(self, percepts):
        surrounding = percepts.get("surrounding", {})
        for pos, contents in surrounding.items():
            type_list = [type(obj).__name__ for obj in contents]
            self.known_map[pos] = type_list
 
            # Update waste map
            waste_here = [obj for obj in contents if isinstance(obj, wasteAgent)]
            if waste_here:
                # Keep all waste entries present on the cell.
                self.waste_entries_map[pos] = [
                    (w.waste_type, getattr(w, "waste_id", None)) for w in waste_here
                ]

                # Backward-compatible single-value views: choose first visible waste.
                self.waste_map[pos] = waste_here[0].waste_type
                self.waste_id_map[pos] = waste_here[0].waste_id
            else:
                # No waste seen here → remove from waste map if present
                self.waste_map.pop(pos, None)
                self.waste_id_map.pop(pos, None)
                self.waste_entries_map.pop(pos, None)
 
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

    # ==================
    # Message processing utilities
    # ==================
    
    # 1. SENDING AND QUEUING MESSAGES
    def _queue_direct_message(self, recipient_id, performative, content):
        message = {
            "mode": "direct",
            "recipient_id": recipient_id,
            "performative": performative,
            "content": content,
        }
        self.pending_messages.append(message)

    def _queue_broadcast_to_color(self, color, performative, content, inventory_state=None):
        message = {
            "mode": "broadcast_color",
            "color": color,
            "performative": performative,
            "content": content,
            "inventory_state": inventory_state,
        }
        self.pending_messages.append(message)

    def _send_if_pending_action(self):
        if not self.pending_messages:
            return None
        return "send_message"
    
    # 2. RECEIVING AND PROCESSING MESSAGES
    def _process_incoming_messages(self):
        new_messages = self.model.get_new_messages(self.agent_id)
        self.received_messages.extend(new_messages)
        for message in new_messages:
            self._handle_message(message)
        # Keep carry_response history by query_id; green agent consumes it when needed.
        

    def _handle_message(self, message):
        # Default behavior: keep message in history only.
        return
    
    # 3. SPECIFIC HANDLERS FOR COMMUNICATION ON DELIVERY
    




# ==================
# Specific agent classes
# ==================

class greenAgent(baseAgent):

    team_color = "green"
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
    
    # ==================
    # Delivery communication for green agents
    # ==================
    # Initie la communication des livraisons
    def _queue_yellow_delivery_query(self):
        """Send carry_query broadcast to all empty yellow robots for yellow waste delivery (once per load)."""
        # Check if we already sent a query for this batch of yellows (avoid resending)
        if getattr(self, "_yellow_query_sent_for_batch", None) == id(self.inventory):
            return False

        # Broadcast carry_query to all empty yellows
        self._queue_broadcast_to_color(
            color="yellow",
            performative="carry_query",
            content={
                "query_id": self.model.next_query_id(),
                "waste_type": "yellow",
            },
        ) 
        self._id_last_query = self.model.next_query_id() - 1
        self._step_last_query = self.current_step
        self._yellow_query_sent_for_batch = id(self.inventory)
        return True
    
    # Verifie qu'il y a eu au moins une réponse de la part des jaunes
    def _handle_message(self, message):
        if message.performative == "carry_response":
            # On garde les ids et positions des jaunes qui ont répondu dans le dictionnaire de self.id_and_position_carrier_response. Les clefs sont l'id de la requête et dont le contenu associé est une liste de liste de [id_agent, pos_agent] des répondants qu'on fait grossir 
            query_id = message.content.get("query_id")
            if query_id not in self.id_and_position_carrier_response:
                self.id_and_position_carrier_response[query_id] = []
            self.id_and_position_carrier_response[query_id].append([message.sender_id, message.content.get("agent_position")])

    # Envoie un message direct au jaune sélectionné pour lui donner les détails de la livraison
    def _queue_detail_delivery(self, recipient_id):
        self._queue_direct_message(
            recipient_id=recipient_id,
            performative="delivery_details",
            content={
                "waste_id": self.waste_id_map.get(self.pos),
                "waste_pos": self.pos,
            },
        )
        
    # Envoie un message direct à tous les jaunes que le waste a été prise (lock) et qu'ils ne doivent pas la prendre (même à celui qui a été sélectionné car dans sas gestion des messages il pourra ignorer le lock)
    def _queue_lock_delivery(self, group):
        self._queue_broadcast_to_color(
            color=group,
            performative="lock_delivery",
            content={
                "waste_id": self.waste_id_map.get(self.pos),
            },
        )
    
    # ==================
    # Deliberation for green agents
    # ==================

    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]

        send_action = self._send_if_pending_action()
        if send_action:
            return send_action

        timeout_action = self._timeout_drop_action()
        if timeout_action:
            return timeout_action

        # Gestion du cas où on doit livrer un déchet jaune à la fronière et qu'on effectue les échanges de communication sur la delivery 
        if "yellow" in inv_types or getattr(self, "_step_last_query", -10) == self.current_step - 2 :
            target_x = self.model.z1[2] - 1  # Z1/Z2 frontier
            
            # Je dois atteindre la frontière 
            if self.pos[0] == target_x:
                
                # Before dropping, broadcast carry_query to all empty yellow robots
                if self._queue_yellow_delivery_query():
                    return "send_message"
            
                # Wait 2 steps for yellow to answer
                # First tempo, drop
                if getattr(self, "_step_last_query", -10) == self.current_step - 1:
                    return "drop"
                
                # Second tempo, all the answers should have had arrived
                if getattr(self, "_step_last_query", -10) == self.current_step - 2:
                    # Sélectionner le jaune qui est le plus proche de moi parmi ceux qui ont répondu positivement
                    candidates = self.id_and_position_carrier_response.get(getattr(self, "_id_last_query", None), [])
                    if candidates:
                        closest = min(candidates, key=lambda c: manhattan(self.pos, c[1]))
                        # Ajouter dans les pendings messages un message direct à ce jaune pour lui donner les détails de la livraison (id de la waste à prendre, etc.)
                        self._queue_detail_delivery(recipient_id=closest[0])
                        # Envoyer un lock à tous les autres jaunes pour ne pas qu'ils le prennent
                        self._queue_lock_delivery("yellow")
                        return "send_message"
                    
                
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
            p for p, entries in self.waste_entries_map.items()
            if self.model.is_position_allowed(self, p)
            and not (p[0] == border_x and len(self.inventory) == 0)
            and any(wt == "green" and self._is_waste_id_allowed(wid) for wt, wid in entries)
        ]
        if green_targets:
            closest = min(green_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        return self._explore_action()

class yellowAgent(baseAgent):
 
    team_color = "yellow"
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
    
    # ==================
    # Delivery communication for yellow agents
    # ==================
    

    def _handle_message(self, message):
        # Handle carry_query (for yellow wastes)
        if message.performative == "carry_query":
            # carry_query is a broadcast from a green at frontier offering yellow pickup
            sender_id = message.sender_id
            
            # Conditions pour accepter
            inv_types = [w.waste_type for w in self.inventory]
            can_accept = len(self.inventory) == 1 and "yellow" in inv_types and self.assigned_waste_id is None and self.assigned_requester_id is None
            
            # Only a response if we can accept, otherwise we ignore the message and let the requester timeout.
            if can_accept:
                # Accept: move to requester's position to pickup yellow
                self.assigned_requester_id = sender_id
                self._queue_direct_message(
                    recipient_id=sender_id,
                    performative="carry_response",
                    content={
                        "query_id": message.content.get("query_id"),
                        "accepted": True,
                        "agent_position" : self.pos,
                    },
                )
            return
        
        if message.performative == "delivery_details":
            # delivery_details is a direct message from green to yellow with pickup instructions
            waste_id = message.content.get("waste_id")
            waste_pos = message.content.get("waste_pos")
            self.assigned_waste_id = waste_id
            self.assigned_waste_pos = waste_pos
            return
                                            
        if message.performative == "lock_delivery":
            # lock_delivery is a broadcast from a green to all yellows indicating that a specific waste has been assigned and should not be taken by others.
            waste_id = message.content.get("waste_id")
            # s'il n'y a pas eu au préalable un message pour l'assigner alors il faut le lock
            if waste_id != self.assigned_waste_id:
                self.locked_waste_ids.add(waste_id)
            return

    def _resolve_assigned_waste_action(self):
        """Assigned pickup has priority over normal yellow behavior. Handle both waste and requester assignments."""
        # Handle carry_query assignment: navigate to requester to pick up yellow
        if self.assigned_requester_id is not None:
            requester = self.model.agent_index_by_id.get(self.assigned_requester_id)            
            requester_pos = requester.pos
            if requester_pos is None:
                return None
            
            # Check if we're at requester's position and can pick up yellow
            if self.pos == requester_pos:
                current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
                if any(
                    isinstance(obj, wasteAgent)
                    and obj.waste_type == "yellow"
                    and self.can_add_waste_type(obj.waste_type)
                    for obj in current_contents
                ):
                    return "pick_up"
            
            # Navigate to requester
            action = self._move_toward(requester_pos)
            if action:
                return action
            return None

        # Handle carry_request assignment: navigate to waste and pick it up (classic case)
        if self.assigned_waste_pos is not None:
            action = self._move_toward(self.assigned_waste_pos)
            if action:
                return action

        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        if any(
            isinstance(obj, wasteAgent)
            and getattr(obj, "waste_id", None) == self.assigned_waste_id
            and self.can_add_waste_type(obj.waste_type)
            for obj in current_contents
        ):
            return "pick_up"

        for pos, entries in self.waste_entries_map.items():
            if any(wid == self.assigned_waste_id for _, wid in entries):
                self.assigned_waste_pos = pos
                action = self._move_toward(pos)
                if action:
                    return action

        # Assignment appears stale: release it to avoid deadlocks.
        self.assigned_waste_id = None
        self.assigned_waste_pos = None
        return None
 
    # ==================
    # Deliberation for yellow agents (priority to answer communication)
    # ==================
 
    def deliberate(self):
        inv_types = [w.waste_type for w in self.inventory]

        # Strict priority: if a response is queued, sending it consumes this turn.
        send_action = self._send_if_pending_action()
        if send_action:
            return send_action

        # If the assigned waste has been picked up, assignment is fulfilled.
        if self.assigned_waste_id is not None and any(
            getattr(waste, "waste_id", None) == self.assigned_waste_id for waste in self.inventory
        ):
            self.assigned_waste_id = None
            self.assigned_waste_pos = None

        # If yellow was picked up via carry_query, release the requester assignment.
        if self.assigned_requester_id is not None and any(
            waste.waste_type == "yellow" for waste in self.inventory
        ):
            self.assigned_requester_id = None

        assigned_action = self._resolve_assigned_waste_action()
        if assigned_action:
            return assigned_action
        
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
            p for p, entries in self.waste_entries_map.items()
            if self.model.is_position_allowed(self, p)
            and any(
                (
                    wt == "green"
                    and p[0] == frontier_x
                    and len(self.inventory) == 0
                    and self._is_waste_id_allowed(wid)
                )
                or (
                    wt == "yellow"
                    and not (p[0] == right_border_x and "yellow" not in inv_types)
                    and self._is_waste_id_allowed(wid)
                )
                for wt, wid in entries
            )
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
            if random.random() < 0.2:
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
 
    team_color = "red"
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1

    def __init__(self, model, agent_id=None):
        super().__init__(model, agent_id=agent_id)
        self.known_disposal_zone = None
        self.column_to_scan_for_deposital = self.model.grid.width - 2 # For initial disposal search pattern
        self.scan_direction = None

    # ==================
    # Disposal zone discovery and communication
    # ==================
    
    def _handle_message(self, message):
        if message.performative != "disposal_found":
            return
        position = message.content.get("position")
        if isinstance(position, tuple) and len(position) == 2:
            self.known_disposal_zone = position

    def _discover_disposal_zone(self):
        for pos, contents in self.percepts.get("surrounding", {}).items():
            for obj in contents:
                if isinstance(obj, radioactivityAgent) and obj.radioactivity == 10:
                    first_discovery = self.known_disposal_zone is None
                    self.known_disposal_zone = pos
                    return first_discovery
        return False

    def _initial_disposal_search_action(self):
        # First move to the column_to_scan_for_deposital (penultimate column).
        if self.pos[0] != self.column_to_scan_for_deposital:
            action = self._move_toward((self.column_to_scan_for_deposital, self.pos[1]))
            return action or self._explore_action()

        # Once on scan column, choose a random vertical strategy and keep it
        # until blocked (agent or boundary), then switch direction.
        if self.scan_direction is None:
            self.scan_direction = random.choice(["up", "down"])

        safe_actions = {name: target for name, target in self._safe_move_actions(self.percepts)}
        preferred_action = "move_up" if self.scan_direction == "up" else "move_down"
        opposite_action = "move_down" if preferred_action == "move_up" else "move_up"

        if preferred_action in safe_actions and safe_actions[preferred_action][0] == self.column_to_scan_for_deposital:
            return preferred_action

        # Obstacle encountered in preferred direction -> switch strategy.
        self.scan_direction = "down" if self.scan_direction == "up" else "up"
        if opposite_action in safe_actions and safe_actions[opposite_action][0] == self.column_to_scan_for_deposital:
            return opposite_action

        # If both vertical moves are blocked, temporarily sidestep to reduce clogging.
        if "move_left" in safe_actions:
            return "move_left"
        return None
    
    # ==================
    # Red agent verificiation methods
    # ==================

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
    
    # ==================
    # Red agent main deliberation method
    # ==================
 
    def deliberate(self):
        discovery_is_new = self._discover_disposal_zone()
        if discovery_is_new :
            self._queue_broadcast_to_color(
                color="red",
                performative="disposal_found",
                content={"position": self.known_disposal_zone},
            )

        send_action = self._send_if_pending_action()
        if send_action:
            return send_action

        if self.known_disposal_zone is None:
            return self._initial_disposal_search_action()

        inv_types = [w.waste_type for w in self.inventory]

        # Red direct-handoff mode is mandatory for any carried waste.
        if self.inventory:
            self.direct_handoff_mode = True
            target = self.known_disposal_zone
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
            p for p, entries in self.waste_entries_map.items()
            if self.model.is_position_allowed(self, p)
            and any(
                (
                    wt == "red"
                    and self._is_waste_id_allowed(wid)
                )
                or (
                    wt in {"green", "yellow"}
                    and p[0] == frontier_x
                    and self._is_waste_id_allowed(wid)
                )
                for wt, wid in entries
            )
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