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
from policies import build_policy

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

    def __init__(self, model, agent_id=None, policy=None, policy_profile=None):
        super().__init__(model)
        self.agent_id = agent_id
        self.current_step = 0
        self.percepts = {}
        self.inventory = []        
        self.carry_steps = 0
        self.policy_profile = policy_profile
        self.policy = policy or build_policy(getattr(self, "team_color", None), policy_profile)

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
        self.id_and_position_carrier_response = {}
        self.id_last_query = None
        self.step_last_query = None
        self.query_sent_for_batch = None
        self.carry_response_query_id = None
        self.blocked_from_pickup_until = -1
        self.state_change_freeze_until = -1
        self.carry_response_lock_until = -1
        self.last_dropped_waste_id = None
        self.last_dropped_waste_type = None
        self.last_dropped_waste_pos = None


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
        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.update(new_percepts)
        self.current_step += 1

    def _carry_step_limit(self):
        """Return carry timeout in number of steps, based on grid size."""
        return (self.model.grid.width + self.model.grid.height)/2

    def _eastern_border_x(self):
        """Return the easternmost x-column allowed for this agent."""
        zone_bounds = {
            "z1": self.model.z1,
            "z2": self.model.z2,
            "z3": self.model.z3,
        }
        right_cols = [zone_bounds[z][2] - 1 for z in self.allowed_zones if z in zone_bounds]
        return max(right_cols)
    
    def _western_border_x(self):
        """Return the westernmost x-column of his allowed area for this agent."""
        zone_bounds = {
            "z1": self.model.z1,
            "z2": self.model.z2,
            "z3": self.model.z3,
        }
        # 
        z = self.allowed_zones[-1]  
        return zone_bounds[z][0] - 1 

    def _timeout_drop_action(self, target_x, performative, receiving_group, waste_type):
        """If carrying for too long, force move to eastern border then drop."""
        if not self.inventory:
            return None
        if self.carry_steps < self._carry_step_limit():
            return None
        return self._deliver(target_x=target_x, performative=performative, receiving_group=receiving_group, waste_type=waste_type)

    def _known_targets_on_frontier(self, waste_type, frontier_x):
        """Return known positions of given waste type located on frontier column."""
        targets = []
        for p, entries in self.waste_entries_map.items():
            if p[0] != frontier_x or not self.model.is_position_allowed(self, p):
                continue
            if any(wt == waste_type and self._can_add_waste_type(wt, wid, p) for wt, wid in entries):
                targets.append(p)
        return targets

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
    
    def _can_add_waste_type(self, waste_type, waste_id, waste_pos):
        if len(self.inventory) >= self.max_capacity:
            return False
        
        if waste_id in self.locked_waste_ids and waste_id != self.assigned_waste_id:
            return False
        
        # If carrying a non-native waste, this must remain the only carried item.
        if any(w.waste_type != self.target_waste_type for w in self.inventory):
            return False
        
        left_border_x = self._eastern_border_x()
        right_border_x = self._western_border_x()
        inv_types = [w.waste_type for w in self.inventory]
        
        if self.team_color == "green":
            if waste_type != "green":
                return False
            # Green agent cannot pick a green at Z1/Z2 frontier when empty.
            if waste_pos[0] == left_border_x and len(self.inventory) == 0:
                return False
            return True

        if self.team_color == "yellow":
            if waste_type == "green":
                # Yellow can carry green only from Z1/Z2 frontier, and only with empty inventory.
                return waste_pos[0] == right_border_x and len(self.inventory) == 0

            if waste_type == "yellow":
                # If carrying green, yellow must remain the only item.
                if "green" in inv_types or "red" in inv_types:
                    return False
                # At Z2/Z3 frontier, yellow can be picked only if already carrying yellow.
                if waste_pos[0] == left_border_x and "yellow" not in inv_types:
                    return False
                return True
            # Yellow agent never picks red from the floor.
            return False
        
        if self.team_color == "red":
            if waste_type in {"green", "yellow"}:
                # Red can pick green/yellow only on Z2/Z3 frontier.
                return waste_pos[0] == right_border_x and len(self.inventory) == 0
            if waste_type == "red":
                return True
            return False
 

    def deliberate(self, knowledge=None):
        raise NotImplementedError("This method should be implemented by subclasses")

    # ==================
    # Delivery action with communication for agents
    # ==================
    # Initie la communication des livraisons
    def _queue_delivery_query(self, performative, receiving_group, waste_type):
        """Send carry_query broadcast to all empty yellow robots for yellow waste delivery (once per load)."""
        # Check if we already sent a query for this batch of yellows (avoid resending)
        if getattr(self, "query_sent_for_batch", None) == self.inventory[0].waste_id :
            return False
        
        # Broadcast carry_query to all full yellows
        self._queue_broadcast_to_color(
            color=receiving_group,
            performative=performative,
            content={
                "query_id": self.model.next_query_id(),
                "waste_type": waste_type,
            },
        ) 
        self.id_last_query = self.model.next_query_id() - 1
        self.step_last_query = self.current_step
        self.query_sent_for_batch = self.inventory[0].waste_id
        return True
    
    def _accept_delivery_query(self, message):
        # Accept: send an acceptance message of the query request
        # Seulement si n'a pas déjà accepté une query récemment
        if self.current_step >= getattr(self, "carry_response_lock_until", -1):
            sender_id = message.sender_id
            self._queue_direct_message(
                recipient_id=sender_id,
                performative="carry_response",
                content={
                    "query_id": message.content.get("query_id"),
                    "accepted": True,
                    "agent_position" : self.pos,
                },
            )
            # BLOQUER les pickups pour l'étape suivante (en cas de delivery_details)
            self.blocked_from_pickup_until = self.current_step + 2
            # During this short freeze window, keep inventory/state stable until assignment orchestration settles.
            self.state_change_freeze_until = self.current_step + 2
            # Bloquer les réponses à d'autres queries de livraison pendant un certain nombre d'étapes pour éviter les conflits et les réponses multiples
            self.carry_response_lock_until = self.current_step + 2

    # Envoie un message direct au robot sélectionné pour lui donner les détails de la livraison
    def _queue_detail_delivery(self, recipient_id, waste_id, waste_pos):
        self._queue_direct_message(
            recipient_id=recipient_id,
            performative="delivery_details",
            content={
                "waste_id": waste_id,
                "waste_pos": waste_pos,
            },
        )
        
    # Envoie un message broadcast à tous les robots d'une couleur pour leur indiquer qu'un déchet est sûrement présent à la frontière
    def _queue_broadcast_waste_presence(self, receiving_group, waste_id, waste_type, waste_pos):
        self._queue_broadcast_to_color(
            color=receiving_group,
            performative="waste_presence",
            content={
                "waste_type" : waste_type,
                "waste_pos" : waste_pos,
                "waste_id" : waste_id,
            },
        )

    # Envoie un message direct à tous les robots que le waste a été assigné (lock) et qu'ils ne doivent pas la prendre (même à celui qui a été sélectionné car dans sas gestion des messages il pourra ignorer le lock)
    def _queue_lock_delivery(self, receiving_group, waste_id):
        self._queue_broadcast_to_color(
            color=receiving_group,
            performative="lock_delivery",
            content={
                "waste_id": waste_id,
            },
        )

    # Gère la logique de livraison à la frontière avec les échanges de messages : se déplacer vers la frontière, envoyer les messages de coordination, attendre les réponses, sélectionner le transporteur, envoyer les détails, etc.
    def _deliver(self, target_x, performative, receiving_group, waste_type):
         # Je dois atteindre la frontière 
        if self.pos[0] == target_x:
            # Tout ce qui passe avant le drop
            if len(self.inventory) != 0 : 
                # Before dropping, broadcast carry_query to all robots that can handle the delivery
                if self._queue_delivery_query(performative=performative, receiving_group=receiving_group, waste_type=waste_type):
                    return "send_message"
            
                # Wait 2 steps for yellow to answer
                # First tempo, drop
                if getattr(self, "step_last_query", -10) == self.current_step - 1: 
                    return "drop"
            
            # Second tempo après le drop, all the answers should have had arrived
            if getattr(self, "step_last_query", -10) == self.current_step - 2:
                dropped_waste_id = self.last_dropped_waste_id
                dropped_waste_type = self.last_dropped_waste_type
                dropped_waste_pos = self.last_dropped_waste_pos

                # Parcours des robots qui ont répondu
                candidates = self.id_and_position_carrier_response.get(getattr(self, "id_last_query", None), [])
                
                # Si au moins une réponse
                if candidates:
                    # Déterminer le robot le plus proche parmi les répondants
                    closest = min(candidates, key=lambda c: manhattan(self.pos, c[1]))
                    # Ajouter dans les pendings messages un message direct à ce jaune pour lui donner les détails de la livraison (id de la waste à prendre, etc.)
                    self._queue_detail_delivery(
                        recipient_id=closest[0],
                        waste_id=dropped_waste_id,
                        waste_pos=dropped_waste_pos,
                    )
                    # Envoyer un lock à tous les autres jaunes pour ne pas qu'ils le prennent
                    self._queue_lock_delivery(
                        receiving_group=receiving_group,
                        waste_id=dropped_waste_id,
                    )
                
                # Pas de réponse
                else :
                    # On peut faire un broadcast pour indiquer la présence du déchet à la frontière
                    self._queue_broadcast_waste_presence(
                        receiving_group=receiving_group,
                        waste_id=dropped_waste_id,
                        waste_type=dropped_waste_type,
                        waste_pos=dropped_waste_pos,
                    )
            
            self.id_last_query = None
            self.step_last_query = None
            self.query_sent_for_batch = None    
            return "send_message"

        action = self._move_toward((target_x, self.pos[1]))
        return action or self._explore_action()
   
    # ==================
    # Handling incoming messages for delivery coordination and other
    # ==================
    def _handle_message(self, message):
        if self.policy is not None:
            return self.policy.handle_message(self, message)
        return None
        
    # ==================
    # Resolve assigned waste action
    # ==================
        
    def _resolve_assigned_waste_action(self):
        """Assigned pickup has priority over normal behavior. Handle both waste and requester assignments."""
        # Handle carry_request assignment: navigate to waste and pick it up (classic case)
        if self.assigned_waste_pos is not None:
            action = self._move_toward(self.assigned_waste_pos)
            if action:
                return action

        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        # Gestion du cas où l'objet dont l'id a été assigné est présent
        if any(
            isinstance(obj, wasteAgent)
            and obj.waste_id == self.assigned_waste_id
            and self._can_add_waste_type(obj.waste_type, obj.waste_id, obj.pos)
            for obj in current_contents
        ):
            # Assignment appears stale: release it to avoid deadlocks.
            if self.current_step >= getattr(self, "blocked_from_pickup_until", -1):
                self.assigned_waste_id = None
                self.assigned_waste_pos = None
                return "pick_up"

        # # S'attribue un nouveau waste si l'ancien non présent
        # for pos, entries in self.waste_entries_map.items():
        #     if any(wid == self.assigned_waste_id for _, wid in entries):
        #         self.assigned_waste_pos = pos
        #         action = self._move_toward(pos)
        #         if action:
        #             return action
        return None

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

# ==================
# SPECIFIC AGENT CLASSES
# ==================

class greenAgent(baseAgent):

    team_color = "green"
    allowed_zones = ["z1"]
    target_waste_type = "green"
    result_waste_type = "yellow"
    max_capacity = 2
    
    # ==================
    # Deliberation for green agents
    # ==================

    def deliberate(self):
        return self.policy.deliberate(self)

class yellowAgent(baseAgent):
 
    team_color = "yellow"
    target_waste_type = "yellow"
    result_waste_type = "red"
    allowed_zones = ["z1", "z2"]
    max_capacity = 2

    # ==================
    # Deliberation for yellow agents (priority to answer communication)
    # ==================
 
    def deliberate(self):
        return self.policy.deliberate(self)

class redAgent(baseAgent):
 
    team_color = "red"
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1

    def __init__(self, model, agent_id=None, policy=None, policy_profile=None):
        super().__init__(model, agent_id=agent_id, policy=policy, policy_profile=policy_profile)
        self.known_disposal_zone = None
        self.column_to_scan_for_deposital = self.model.grid.width - 2 # For initial disposal search pattern
        self.scan_direction = None

    # ==================
    # Disposal zone discovery and communication
    # ==================

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
    # Red agent main deliberation method
    # ==================
 
    def deliberate(self):
        return self.policy.deliberate(self)
