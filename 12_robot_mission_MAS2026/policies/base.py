"""Shared policy helpers and abstract base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
import random

from objects import wasteAgent


# ======= SHARED HELPERS ======
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def frontier_action(agent, target_x):
    if agent.pos[0] == target_x:
        return "drop"
    action = agent._move_toward((target_x, agent.pos[1]))
    return action or agent._explore_action()

# ====== TIMEOUT ACTION WITHOUT COMMUNICATION ======
def no_communication_timeout_action(agent, target_x):
    if not agent.inventory:
        return None
    if agent.carry_steps < agent._carry_step_limit():
        return None
    return frontier_action(agent, target_x)

# ====== MESSSAGE HANDLING ======
def handle_carry_query(agent, message):
    # Conditions for accepting a carry query:
    inv_types = [w.waste_type for w in agent.inventory]
    can_accept_not_empty = (
        len(agent.inventory) == 1
        and message.content.get("waste_type") in inv_types
        and agent.assigned_waste_id is None
    )
    can_accept_empty = len(agent.inventory) == 0 and agent.assigned_waste_id is None

    # Only a response if able to accept, otherwise ignore the query and let the sender timeout
    if can_accept_not_empty and message.performative == "carry_query_not_empty":
        agent._accept_delivery_query(message)
    if can_accept_empty and message.performative == "carry_query_empty":
        agent._accept_delivery_query(message)


def handle_carry_response(agent, message):
    """ Keeping ids and positions fo the responding agents dans le dictionnaire id_and_position_carrier_response."""
    query_id = message.content.get("query_id")
    if query_id not in agent.id_and_position_carrier_response:
        agent.id_and_position_carrier_response[query_id] = []
    agent.id_and_position_carrier_response[query_id].append([message.sender_id, message.content.get("agent_position")])


def handle_delivery_details(agent, message):
    """ Handle direct message from a carrier with the details of the delivery assignment, and update the agent's assigned waste accordingly."""
    waste_id = message.content.get("waste_id")
    waste_pos = message.content.get("waste_pos")
    agent.assigned_waste_id = waste_id
    agent.assigned_waste_pos = waste_pos
    agent.locked_waste_ids.discard(waste_id)


def handle_lock_delivery(agent, message):
    """Handle a broadcast message for lock waste """   
    waste_id = message.content.get("waste_id")
    # If the waste already assignated before the lock, ignore the locking
    if waste_id != agent.assigned_waste_id:
        agent.locked_waste_ids.add(waste_id)


def handle_waste_presence(agent, message):
    """ Handle a waste presence by updating the agents "maps knowledge" """
    waste_type = message.content.get("waste_type")
    waste_pos = message.content.get("waste_pos")
    waste_id = message.content.get("waste_id")

    if waste_pos not in agent.waste_entries_map:
        agent.waste_entries_map[waste_pos] = [(waste_type, waste_id)]
    else:
        agent.waste_entries_map[waste_pos].append((waste_type, waste_id))
    # Backward-compatible single value : choose first visible waste.
    agent.waste_map[waste_pos] = waste_type
    agent.waste_id_map[waste_pos] = waste_id


def handle_disposal_found(agent, message):
    """ Handle a disposal found message only for red agents"""
    position = message.content.get("position")
    if isinstance(position, tuple) and len(position) == 2:
        agent.known_disposal_zone = position


def handle_exploration_positions_share(agent, message):
    """Merge explored core positions shared by same-color agents."""
    positions = message.content.get("positions", [])
    for pos in positions:
        x, y = pos
        agent.shared_explored_core_positions.add((x, y))
        agent.target_pos_explo = None  # Reset exploration target to trigger new target selection


def handle_standard_message(agent, message):
    """ Redirect the appropriate handling depending on the performative of the message."""
    if message.performative in {"carry_query_not_empty", "carry_query_empty"}:
        handle_carry_query(agent, message)
        return

    if message.performative == "carry_response":
        handle_carry_response(agent, message)
        return

    if message.performative == "delivery_details":
        handle_delivery_details(agent, message)
        return

    if message.performative == "lock_delivery":
        handle_lock_delivery(agent, message)
        return

    if message.performative == "waste_presence":
        handle_waste_presence(agent, message)
        return

    if message.performative == "disposal_found":
        handle_disposal_found(agent, message)
        return

    if message.performative == "exploration_positions_share":
        handle_exploration_positions_share(agent, message)


# ====== GREEN : DELIBERATION FUNCTIONS ======
""" ********* BASIC POLICY ********** """
def deliberate_green_no_communication(agent):
    """ Very basic policy for green agents without communication.
    Priority in order : 
    - Timeout of green waste
    - Yellow delivery
    - Transform green waste
    - Pick up of green waste
    - Movement toward known green waste
    - Exploration
    """
    inv_types = [w.waste_type for w in agent.inventory]

    # Timeout of green waste
    timeout_action = no_communication_timeout_action(agent, agent._eastern_border_x())
    if timeout_action:
        return timeout_action

    # Yellow delivery
    if "yellow" in inv_types:
        return frontier_action(agent, agent._eastern_border_x())

    # Transformation
    if inv_types.count("green") >= 2:
        return "transform"

    # Pick up of green waste if able to
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if any(isinstance(o, wasteAgent) and agent._can_add_waste_type(o.waste_type, o.waste_id, o.pos) for o in current_contents):
        return "pick_up"

    # Move toward known green waste if any in his map knowledge
    green_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(wt == "green" and agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]
    if green_targets:
        closest = min(green_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration
    return agent._explore_action()


""" ********* COMMUNICATION POLICY ********** """
def deliberate_green_with_communication(agent):
    """ Sophisticated policy for green agents with communication: in addition to the basic policy, communication sent when delivering. 
    Same priority order but with coordination for delivery.
    - Timeout of green waste
    - Yellow delivery
    - Smart exploration sharing if enabled and due
    - Transform green waste
    - Pick up of green waste
    - Movement toward known green waste
    - Exploration
    """
    inv_types = [w.waste_type for w in agent.inventory]

    # Timeout of green waste : green delivery
    timeout_action = agent._timeout_drop_action(
        target_x=agent._eastern_border_x(),
        performative="carry_query_empty",
        receiving_group="yellow",
        waste_type="green",
    )
    if timeout_action:
        return timeout_action

    # Yellow delivery
    if "yellow" in inv_types or getattr(agent, "step_last_query", -10) == agent.current_step - 2:
        return agent._deliver(
            target_x=agent._eastern_border_x(),
            performative="carry_query_not_empty",
            receiving_group="yellow",
            waste_type="yellow",
        )

    # Smart exploration sharing (after yellow delivery priority).
    share_action = agent.queue_exploration_share_if_due(interval_steps=30)
    if share_action:
        return share_action

    # Transformation
    if inv_types.count("green") >= 2:
        return "transform"

    # Green pick up if able to
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if any(isinstance(o, wasteAgent) and agent._can_add_waste_type(o.waste_type, o.waste_id, o.pos) for o in current_contents):
        return "pick_up"

    # Move toward known green waste if any in his map knowledge
    green_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(wt == "green" and agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]
    if green_targets:
        closest = min(green_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration if no other action available
    return agent._explore_action()

# ====== YELLOW : DELIBERATION FUNCTIONS ======
""" ********* BASIC POLICY ********** """
def deliberate_yellow_no_communication(agent):
    """ Very basic policy for yellow agents without communication.
    Priority in order : 
    - Timeout of yellow waste
    - Green or red delivery
    - Transform yellow waste
    - Pick up of yellow waste
    - Movement toward known green or yellowwaste
    - Exploration
    """
    inv_types = [w.waste_type for w in agent.inventory]

    # Timeout of yellow waste
    timeout_action = no_communication_timeout_action(agent, agent._eastern_border_x())
    if timeout_action:
        return timeout_action

    # Green or red delivery
    if "green" in inv_types or "red" in inv_types:
        return frontier_action(agent, agent._eastern_border_x())

    # Transformation
    if inv_types.count("yellow") == 2:
        return "transform"

    # Pick up of yellow waste
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
        if any(isinstance(o, wasteAgent) and agent._can_add_waste_type(o.waste_type, o.waste_id, o.pos) for o in current_contents):
            return "pick_up"

    # Movement toward known yellow waste
    yellow_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]
    if yellow_targets:
        closest = min(yellow_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration
    if agent.scout_target is None or agent.pos == agent.scout_target:
        x_min, y_min, x_max, y_max = agent.model.z2
        rand_x = random.randint(x_min, x_max - 2)
        rand_y = random.randint(y_min, y_max - 2)
        agent.scout_target = (rand_x, rand_y)

    action = agent._move_toward(agent.scout_target)
    return action or agent._explore_action()

""" ********* COMMUNICATION POLICY ********** """
def deliberate_yellow_with_communication(agent):
    """ Sophisticated policy for yellow agents with communication: in addition to the basic policy, communication sent when delivering. 
    Change in priority order :
    - Direct delivery of green or red waste
    - Answer to delivery queries (green or yellow) if requirements are met
    - Handle assigned delivery if any
    - Timeout of yellow waste if any
    - Smart exploration sharing if enabled and due
    - Transform yellow waste
    - Pick up of yellow waste not locked
    - Movement toward known yellow waste not locked
    - Exploration
    """
    inv_types = [w.waste_type for w in agent.inventory]

    # Direct delivery of green or red waste
    if "green" in inv_types or getattr(agent, "step_last_query", -10) == agent.current_step - 2:
        return agent._deliver(
            target_x=agent._eastern_border_x(),
            performative="carry_query_empty",
            receiving_group="red",
            waste_type="green",
        )

    if "red" in inv_types or getattr(agent, "step_last_query", -10) == agent.current_step - 2:
        return agent._deliver(
            target_x=agent._eastern_border_x(),
            performative="carry_query_empty",
            receiving_group="red",
            waste_type="red",
        )
        
    # Answer to delivery queries (green or yellow) if requirements are met
    send_action = agent._send_if_pending_action()
    if send_action:
        return send_action

    # Handle assigned delivery if any (until taking assigned waste)
    if agent.assigned_waste_id is not None and any(
        getattr(waste, "waste_id", None) == agent.assigned_waste_id for waste in agent.inventory
    ):
        agent.assigned_waste_id = None
        agent.assigned_waste_pos = None
    
    assigned_action = agent._resolve_assigned_waste_action()
    if assigned_action:
        return assigned_action

    # Timeout of yellow waste if any.
    # Lower priority than queued communication and assigned-task resolution.
    timeout_action = agent._timeout_drop_action(
        target_x=agent._eastern_border_x(),
        performative="carry_query_empty",
        receiving_group="red",
        waste_type="yellow",
    )
    if timeout_action:
        return timeout_action

    # Smart exploration sharing (after direct delivery priorities).
    share_action = agent.queue_exploration_share_if_due(interval_steps=30)
    if share_action:
        return share_action

    # Transformation
    if inv_types.count("yellow") == 2:
        return "transform"

    # Pick up of known yellow waste not locked for them
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
        if any(isinstance(o, wasteAgent) and agent._can_add_waste_type(o.waste_type, o.waste_id, o.pos) for o in current_contents):
            return "pick_up"

    # Movement toward known yellow waste not locked for them
    yellow_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]

    if yellow_targets:
        closest = min(yellow_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration
    if agent.scout_target is None or agent.pos == agent.scout_target:
        x_min, y_min, x_max, y_max = agent.model.z2
        rand_x = random.randint(x_min, x_max - 2)
        rand_y = random.randint(y_min, y_max - 2)
        agent.scout_target = (rand_x, rand_y)

    action = agent._move_toward(agent.scout_target)
    return action or agent._explore_action()


# ====== RED : DELIBERATION FUNCTIONS ======
""" ********* BASIC POLICY ********** """
def deliberate_red_no_communication(agent):
    """ Very basic policy for red agents without communication.
    Priority in order : 
    - Search for disposal zone if not known
    - Delivery if one waste in inventory
    - Pick up all the waste types if possible
    - Movement toward known waste of any type
    - Exploration
    """
    # Search for disposal zone if not known
    agent._discover_disposal_zone()
    if agent.known_disposal_zone is None:
        return agent._initial_disposal_search_action()

    # Delivery if one waste in inventory
    if agent.inventory:
        target = agent.known_disposal_zone
        if agent.pos == target:
            return "drop"
        action = agent._move_toward(target)
        return action or agent._explore_action()

    # Pick up all the waste types if possible
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if any(isinstance(o, wasteAgent) for o in current_contents):
        return "pick_up"

    # Movement toward known waste of any type
    red_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]

    if red_targets:
        closest = min(red_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration
    if agent.scout_target is None or agent.pos == agent.scout_target:
        x_min, y_min, x_max, y_max = agent.model.z3
        rand_x = random.randint(x_min, x_max - 2)
        rand_y = random.randint(y_min, y_max - 2)
        agent.scout_target = (rand_x, rand_y)

    action = agent._move_toward(agent.scout_target)
    return action or agent._explore_action()

""" ********* COMMUNICATION POLICY ********** """
def deliberate_red_with_communication(agent):
    """ Sophisticated policy for red agents with communication: in addition to the basic policy, communication sent when delivering. 
    Change in priority order :
    - Search for disposal zone if not known
    - Share discovery of disposal zone with other red agents if first
    - Direct drop to disposal zone if any waste in inventory
    - Answer to delivery queries if requirements are met
    - Handle assigned delivery if any (until taking assigned waste)
    - Smart exploration sharing if enabled and due
    - Pick up of waste not locked
    - Movement toward known waste not locked
    - Exploration
    """
    # Search for disposal zone if not known, and share discovery with other red agents if first
    discovery_is_new = agent._discover_disposal_zone()
    if discovery_is_new:
        agent._queue_broadcast_to_color(
            color="red",
            performative="disposal_found",
            content={"position": agent.known_disposal_zone},
        )

    if agent.known_disposal_zone is None:
        return agent._initial_disposal_search_action()

    # Direct drop to disposal zone if any waste in inventory
    if agent.inventory:
        target = agent.known_disposal_zone
        if agent.pos == target:
            return "drop"
        action = agent._move_toward(target)
        return action or agent._explore_action()

    # Answer to delivery queries if requirements are met
    send_action = agent._send_if_pending_action()
    if send_action:
        return send_action

    # Handle assigned delivery if any (until taking assigned waste)
    if agent.assigned_waste_id is not None and any(
        getattr(waste, "waste_id", None) == agent.assigned_waste_id for waste in agent.inventory
    ):
        agent.assigned_waste_id = None
        agent.assigned_waste_pos = None

    assigned_action = agent._resolve_assigned_waste_action()
    if assigned_action:
        return assigned_action

    # Smart exploration sharing (after direct delivery priority).
    share_action = agent.queue_exploration_share_if_due(interval_steps=30)
    if share_action:
        return share_action

    # Pick up of known waste not locked for them
    current_contents = agent.percepts.get("surrounding", {}).get(agent.pos, [])
    if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
        if any(isinstance(o, wasteAgent) and agent._can_add_waste_type(o.waste_type, o.waste_id, o.pos) for o in current_contents):
            return "pick_up"

    # Movement toward known waste not locked for them
    red_targets = [
        p for p, entries in agent.waste_entries_map.items()
        if agent.model.is_position_allowed(agent, p)
        and any(agent._can_add_waste_type(wt, wid, p) for wt, wid in entries)
    ]

    if red_targets:
        closest = min(red_targets, key=lambda p: manhattan(agent.pos, p))
        if closest == agent.pos:
            if agent.current_step >= getattr(agent, "blocked_from_pickup_until", -1):
                return "pick_up"
        action = agent._move_toward(closest)
        return action or agent._explore_action()

    # Exploration
    if agent.scout_target is None or agent.pos == agent.scout_target:
        x_min, y_min, x_max, y_max = agent.model.z3
        rand_x = random.randint(x_min, x_max - 2)
        rand_y = random.randint(y_min, y_max - 2)
        agent.scout_target = (rand_x, rand_y)

    action = agent._move_toward(agent.scout_target)
    return action or agent._explore_action()


# ====== BASE POLICY CLASS ======
class BasePolicy(ABC):
    """Abstract strategy object used by robot agents."""

    @abstractmethod
    def deliberate(self, agent):
        raise NotImplementedError

    def handle_message(self, agent, message):
        return None
