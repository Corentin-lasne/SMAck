""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent
from objects import wasteAgent
from collections import deque
import random

STALE_WASTE_TIMEOUT = 18
HANDOVER_ACK_TIMEOUT = 6

# Utility functions for pathfinding and movement.

def manhattan(a, b):
    """Return Manhattan distance between two grid positions."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors_4(pos):
    """Return the 4-neighborhood (Von Neumann) of a grid position."""
    x, y = pos
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

class baseAgent(Agent):
    """Shared robot controller.

    Handles the simulation loop contract for each robot: perceive, process incoming
    messages, deliberate one action, and let the environment execute it.
    """

    target_waste_type = None
    result_waste_type = None
    allowed_zones = []
    max_capacity = 2
    agent_role = "base"

    def __init__(self, model):
        super().__init__(model)
        self.percepts = {}
        self.inventory = []

        self.known_map = {}
        self.waste_map = {}
        self.visited = set()
        self.explored_cells = set()

        self.outbox = deque()
        self.pending_query = None
        self.query_replies = []

        self.active_task = None
        self.communication_locked = False
        self.awaiting_assignment_until = -1

        self.disposal_pos_known = None
        self.scan_direction = 1

        self.carry_start_step = {}
        self.last_waste_info_step = {
            "green": -10**9,
            "yellow": -10**9,
            "red": -10**9,
        }
        self.last_explore_share_step = -1
        self.border_waste_locks = {}
        self.waste_known_times = {}
        self.pending_handover_requests = {}

    def _debug(self, event, **payload):
        """Print optional debug traces when model debug mode is enabled."""
        if not getattr(self.model, "debug", False):
            return
        print(f"[DEBUG][step={self.model.steps}][agent={self.unique_id}][{self.agent_role}] {event} {payload}")

    def step(self):
        """Mesa hook: run one full agent cycle."""
        self.step_agent()

    def step_agent(self):
        """Execute perceive -> message processing -> deliberate -> act -> update."""
        self.percepts = self.model.get_percepts(self)
        self.update(self.percepts)

        received_messages = self.model.read_messages(self)
        self.process_messages(received_messages)

        action = self.deliberate()
        new_percepts = self.model.do(self, action)
        self.update(new_percepts)
        self._post_action_bookkeeping()

    def update(self, percepts):
        """Update local maps from latest percepts and clear stale border locks."""
        surrounding = percepts.get("surrounding", {})
        for pos, contents in surrounding.items():
            type_list = [type(obj).__name__ for obj in contents]
            self.known_map[pos] = type_list
 
            waste_here = [obj for obj in contents if isinstance(obj, wasteAgent)]
            if waste_here:
                waste_types_here = sorted({w.waste_type for w in waste_here})
                self.waste_map[pos] = waste_types_here
                for wtype in waste_types_here:
                    self.last_waste_info_step[wtype] = self.model.steps
                    waste_key = (pos, wtype)
                    if waste_key not in self.waste_known_times:
                        self.waste_known_times[waste_key] = {
                            "first_seen": self.model.steps,
                            "last_seen": self.model.steps,
                        }
                        self._debug("waste_known", pos=pos, waste_type=wtype)
                    else:
                        self.waste_known_times[waste_key]["last_seen"] = self.model.steps
            else:
                self.waste_map.pop(pos, None)
                stale_keys = [key for key in self.waste_known_times if key[0] == pos]
                for stale_key in stale_keys:
                    self.waste_known_times.pop(stale_key, None)

            # Auto-clear lock when local perception confirms the border waste is gone.
            lock = self.border_waste_locks.get(pos)
            if lock is not None:
                lock_type = lock.get("waste_type")
                lock_still_present = any(
                    isinstance(obj, wasteAgent) and obj.waste_type == lock_type for obj in contents
                )
                if not lock_still_present:
                    self._release_border_lock(pos)
 
        if self.pos:
            self.visited.add(self.pos)
            self.explored_cells.add(self.pos)

    def process_messages(self, messages):
        """Consume all received messages and update tasks/knowledge accordingly."""
        for message in messages:
            mtype = message.get("type")
            sender = message.get("from")
            payload = message.get("payload", {})

            if mtype == "explored_cells":
                if not self.communication_locked:
                    for pos in payload.get("cells", []):
                        self.explored_cells.add(tuple(pos))
                continue

            if mtype == "waste_broadcast":
                pos = tuple(payload.get("pos", self.pos))
                wtype = payload.get("waste_type")
                if wtype:
                    self.waste_map[pos] = [wtype]
                    self.last_waste_info_step[wtype] = self.model.steps
                    waste_key = (pos, wtype)
                    if waste_key not in self.waste_known_times:
                        self.waste_known_times[waste_key] = {
                            "first_seen": self.model.steps,
                            "last_seen": self.model.steps,
                        }
                    else:
                        self.waste_known_times[waste_key]["last_seen"] = self.model.steps
                    if self._can_accept_broadcast_task(wtype):
                        self.active_task = {
                            "pos": pos,
                            "waste_type": wtype,
                            "deliver_to": payload.get("deliver_to") or self._default_deliver_to_for_waste(wtype),
                            "picked": False,
                        }
                        self.communication_locked = True
                        self._debug("task_assigned", source="broadcast", pos=pos, waste_type=wtype)
                        self._queue_message({
                            "to": sender,
                            "type": "handover_ack",
                            "payload": {
                                "pos": pos,
                                "waste_type": wtype,
                            },
                        })
                continue

            if mtype == "disposal_found":
                pos = payload.get("pos")
                if pos:
                    self.disposal_pos_known = tuple(pos)
                continue

            if mtype == "availability_query":
                if self.communication_locked:
                    continue
                if self._can_reply_to_query(payload):
                    self.awaiting_assignment_until = self.model.steps + 1
                    self._queue_message({
                        "to": sender,
                        "type": "availability_reply",
                        "payload": {
                            "query_id": payload.get("query_id"),
                            "pos": self.pos,
                            "agent_id": self.unique_id,
                        },
                    })
                continue

            if mtype == "availability_reply":
                if self.pending_query and payload.get("query_id") == self.pending_query.get("query_id"):
                    reply_pos = payload.get("pos")
                    reply_agent_id = payload.get("agent_id")
                    if reply_pos is not None and reply_agent_id is not None:
                        self.query_replies.append((reply_agent_id, tuple(reply_pos)))
                continue

            if mtype == "task_assignment":
                assigned_pos = payload.get("pos")
                if assigned_pos is None:
                    continue
                self.active_task = {
                    "pos": tuple(assigned_pos),
                    "waste_type": payload.get("waste_type"),
                    "deliver_to": payload.get("deliver_to"),
                    "picked": False,
                }
                self.pending_query = None
                self.query_replies = []
                self.communication_locked = True
                self.awaiting_assignment_until = -1
                continue

            if mtype == "border_waste_lock":
                pos = payload.get("pos")
                if pos is None:
                    continue
                lock_pos = tuple(pos)
                lock_type = payload.get("waste_type")
                if lock_type:
                    self.border_waste_locks[lock_pos] = {
                        "waste_type": lock_type,
                        "next_role": payload.get("next_role"),
                        "locked_by": sender,
                    }
                continue

            if mtype == "border_waste_unlock":
                pos = payload.get("pos")
                if pos is None:
                    continue
                lock_pos = tuple(pos)
                self.border_waste_locks.pop(lock_pos, None)
                continue

            if mtype == "handover_ack":
                pos = payload.get("pos")
                wtype = payload.get("waste_type")
                if pos is None or wtype is None:
                    continue
                ack_key = (tuple(pos), wtype)
                if ack_key in self.pending_handover_requests:
                    self.pending_handover_requests.pop(ack_key, None)
                    self._debug("handover_ack_received", pos=tuple(pos), waste_type=wtype)

    def _can_reply_to_query(self, payload):
        # Keep one step available for the assignment after a reply.
        if self.awaiting_assignment_until >= self.model.steps and self.active_task is None:
            return False

        required_role = payload.get("role")
        if required_role and required_role != self.agent_role:
            return False

        mode = payload.get("mode")
        waste_type = payload.get("waste_type")

        if mode == "carrying":
            return self._inventory_count(waste_type) > 0
        if mode == "free":
            return len(self.inventory) == 0 and self.active_task is None
        return False

    def _queue_message(self, message):
        self.outbox.append(message)

    def _start_query(self, *, role, mode, waste_type, waste_pos, deliver_to=None, on_no_reply="none"):
        """Start an asynchronous availability query to a role and track replies."""
        query_id = self.model.make_query_id()
        self.pending_query = {
            "query_id": query_id,
            "role": role,
            "mode": mode,
            "waste_type": waste_type,
            "waste_pos": waste_pos,
            "deliver_to": deliver_to,
            "deadline": self.model.steps + 2,
            "on_no_reply": on_no_reply,
        }
        self.query_replies = []
        self._queue_message({
            "to_role": role,
            "type": "availability_query",
            "payload": {
                "query_id": query_id,
                "role": role,
                "mode": mode,
                "waste_type": waste_type,
            },
        })

    def _handle_pending_query(self):
        """Resolve pending query by assigning closest responder or running fallback."""
        if self.pending_query is None:
            return None

        query = self.pending_query
        timed_out = self.model.steps >= query["deadline"]
        has_replies = len(self.query_replies) > 0

        if not timed_out and not has_replies:
            return None

        if has_replies:
            target_agent, _ = min(
                self.query_replies,
                key=lambda item: manhattan(self.pos, item[1]),
            )
            self._queue_message({
                "to": target_agent,
                "type": "task_assignment",
                "payload": {
                    "pos": query["waste_pos"],
                    "waste_type": query["waste_type"],
                    "deliver_to": query.get("deliver_to"),
                },
            })
            self.pending_query = None
            self.query_replies = []
            return None

        if timed_out:
            fallback = query.get("on_no_reply")
            waste_pos = query.get("waste_pos")
            waste_type = query.get("waste_type")
            target_role = query.get("role")
            self.pending_query = None
            self.query_replies = []

            if fallback == "pickup_if_here" and waste_pos == self.pos and self._can_pick_waste_type(waste_type):
                return "pick_up"

            if fallback == "broadcast_position":
                self._queue_message({
                    "to_role": target_role,
                    "type": "waste_broadcast",
                    "payload": {
                        "pos": waste_pos,
                        "waste_type": waste_type,
                        "deliver_to": query.get("deliver_to"),
                    },
                })

        return None

    def _can_accept_broadcast_task(self, waste_type):
        if self.communication_locked:
            return False
        if self.active_task is not None:
            return False
        if len(self.inventory) >= self.max_capacity:
            return False
        if len(self.inventory) == 0:
            return True
        return self._inventory_count(waste_type) > 0

    def _default_deliver_to_for_waste(self, waste_type):
        if self.agent_role == "yellow":
            if waste_type == "green":
                return "z2_east"
            if waste_type == "yellow":
                return "z2_east"
            if waste_type == "red":
                return "z2_east"
        if self.agent_role == "red":
            return "disposal"
        return None

    def _inventory_count(self, waste_type):
        return sum(1 for w in self.inventory if w.waste_type == waste_type)

    def _waste_age(self, pos, waste_type):
        times = self.waste_known_times.get((pos, waste_type))
        if times is None:
            return 0
        return self.model.steps - times["first_seen"]

    def _is_stale_waste(self, pos, waste_type):
        return self._waste_age(pos, waste_type) >= STALE_WASTE_TIMEOUT

    def _is_waste_assigned(self, pos, waste_type):
        for other in self.model.robotAgents:
            task = getattr(other, "active_task", None)
            if task is None:
                continue
            if tuple(task.get("pos", (-1, -1))) == pos and task.get("waste_type") == waste_type:
                return True
        return False

    def _register_handover_request(self, pos, waste_type, next_role, deliver_to):
        self.pending_handover_requests[(pos, waste_type)] = {
            "next_role": next_role,
            "deliver_to": deliver_to,
            "deadline": self.model.steps + HANDOVER_ACK_TIMEOUT,
        }

    def _handover_recovery_action(self):
        # Policy gap: border waste can remain without explicit pickup acknowledgment.
        expired = []
        for (pos, waste_type), state in self.pending_handover_requests.items():
            if self.model.steps < state["deadline"]:
                continue

            known_types = self.waste_map.get(pos, [])
            if waste_type not in known_types:
                expired.append((pos, waste_type))
                continue

            self._debug("handover_retry", pos=pos, waste_type=waste_type, next_role=state["next_role"])
            self._start_query(
                role=state["next_role"],
                mode="free",
                waste_type=waste_type,
                waste_pos=pos,
                deliver_to=state.get("deliver_to"),
                on_no_reply="broadcast_position",
            )
            state["deadline"] = self.model.steps + HANDOVER_ACK_TIMEOUT
            send_action = self._send_next_message_action()
            if send_action:
                return send_action

        for key in expired:
            self.pending_handover_requests.pop(key, None)
        return None

    def _stale_recovery_action(self):
        # Policy gap: known waste can remain unassigned forever if communication chain fails.
        if self.active_task is not None:
            return None

        candidates = []
        for pos, waste_types in self.waste_map.items():
            for waste_type in waste_types:
                if not self.model.is_position_allowed(self, pos):
                    continue
                if self._is_waste_assigned(pos, waste_type):
                    continue
                if not self._is_stale_waste(pos, waste_type):
                    continue
                candidates.append((pos, waste_type))

        if not candidates:
            return None

        pos, waste_type = min(candidates, key=lambda item: manhattan(self.pos, item[0]))
        self._debug("waste_ignored_too_long", pos=pos, waste_type=waste_type, age=self._waste_age(pos, waste_type))
        self.active_task = {
            "pos": pos,
            "waste_type": waste_type,
            "deliver_to": self._default_deliver_to_for_waste(waste_type),
            "picked": False,
        }
        self.communication_locked = True
        self._debug("task_assigned", source="stale_recovery", pos=pos, waste_type=waste_type)
        return self._task_action()

    def _is_locked_for_pickup(self, pos, waste_type):
        lock = self.border_waste_locks.get(pos)
        if lock is None:
            return False
        if lock.get("waste_type") != waste_type:
            return False
        if self._is_stale_waste(pos, waste_type):
            return False
        # An agent carrying the same waste type may still combine two units.
        return self._inventory_count(waste_type) == 0

    def _release_border_lock(self, pos):
        lock = self.border_waste_locks.pop(pos, None)
        if lock is None:
            return
        self._queue_message({
            "to_role": self.agent_role,
            "type": "border_waste_unlock",
            "payload": {
                "pos": pos,
                "waste_type": lock.get("waste_type"),
            },
        })

    def _lock_border_waste(self, pos, waste_type, next_role):
        self.border_waste_locks[pos] = {
            "waste_type": waste_type,
            "next_role": next_role,
            "locked_by": self.unique_id,
        }
        self._queue_message({
            "to_role": self.agent_role,
            "type": "border_waste_lock",
            "payload": {
                "pos": pos,
                "waste_type": waste_type,
                "next_role": next_role,
                "reserved_for": next_role,
            },
        })

    def _can_pick_waste_type(self, waste_type):
        if len(self.inventory) >= self.max_capacity:
            return False
        if self._is_locked_for_pickup(self.pos, waste_type):
            return False
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        return any(isinstance(o, wasteAgent) and o.waste_type == waste_type for o in current_contents)

    def _message_priority(self, message):
        mtype = message.get("type")
        if mtype in {"task_assignment", "availability_query", "availability_reply", "waste_broadcast", "disposal_found", "border_waste_lock", "border_waste_unlock"}:
            return 0
        if mtype == "explored_cells":
            return 5
        return 2

    def _send_next_message_action(self):
        if not self.outbox:
            return None

        best_message = min(self.outbox, key=self._message_priority)
        self.outbox.remove(best_message)
        return {
            "type": "send_message",
            "message": best_message,
        }

    def _broadcast_exploration_if_needed(self):
        if self.model.steps == 0:
            return
        if self.model.steps % 20 != 0:
            return
        if self.last_explore_share_step == self.model.steps:
            return
        self.last_explore_share_step = self.model.steps
        self._queue_message({
            "to_role": self.agent_role,
            "type": "explored_cells",
            "payload": {
                "cells": list(self.explored_cells),
            },
        })

    def _task_drop_target(self, deliver_to, waste_type):
        if deliver_to == "z1_east":
            return (self.model.z1[2] - 1, self.pos[1])
        if deliver_to == "z2_east":
            return (self.model.z2[2] - 1, self.pos[1])
        if deliver_to == "disposal":
            return self.disposal_pos_known or self.model.waste_disposal_zone

        if waste_type == "red":
            return self.disposal_pos_known or self.model.waste_disposal_zone
        if waste_type == "yellow":
            return (self.model.z2[2] - 1, self.pos[1])
        if waste_type == "green":
            return (self.model.z1[2] - 1, self.pos[1])
        return self.pos

    def _task_action(self):
        """Return the next action for the currently assigned communication task."""
        if self.active_task is None:
            return None

        task = self.active_task
        task_waste = task.get("waste_type")
        target_pos = tuple(task.get("pos", self.pos))

        if self._inventory_count(task_waste) > 0:
            task["picked"] = True

        if not task.get("picked", False):
            if self.pos == target_pos and self._can_pick_waste_type(task_waste):
                return "pick_up"
            return self._move_toward(target_pos) or self._explore_action()

        drop_target = self._task_drop_target(task.get("deliver_to"), task_waste)
        if self.pos == drop_target:
            border_drop = self._border_drop_descriptor()
            if border_drop is not None:
                handover_deliver_to = "z2_east" if border_drop["next_role"] == "yellow" else "disposal"
                self._lock_border_waste(
                    self.pos,
                    border_drop["waste_type"],
                    border_drop["next_role"],
                )
                self._register_handover_request(
                    self.pos,
                    border_drop["waste_type"],
                    border_drop["next_role"],
                    handover_deliver_to,
                )
            return "drop"
        return self._move_toward(drop_target) or self._explore_action()

    def _common_priority_action(self):
        """Resolve communication-priority behaviors before exploration heuristics."""
        handover_action = self._handover_recovery_action()
        if handover_action:
            return handover_action

        self._broadcast_exploration_if_needed()

        pending_action = self._handle_pending_query()
        if pending_action:
            return pending_action

        task_action = self._task_action()
        if task_action:
            return task_action

        send_action = self._send_next_message_action()
        if send_action:
            return send_action

        stale_action = self._stale_recovery_action()
        if stale_action:
            return stale_action

        return None

    def _on_cell_has_waste(self, waste_type):
        if self._is_locked_for_pickup(self.pos, waste_type):
            return False
        current_contents = self.percepts.get("surrounding", {}).get(self.pos, [])
        return any(isinstance(o, wasteAgent) and o.waste_type == waste_type for o in current_contents)

    def _known_targets(self, waste_type):
        targets = []
        for pos, types_here in self.waste_map.items():
            if self._is_locked_for_pickup(pos, waste_type):
                continue
            if waste_type in types_here and self.model.is_position_allowed(self, pos):
                targets.append(pos)
        return targets

    def _carry_timeout_reached(self, waste_type):
        if self._inventory_count(waste_type) == 0:
            return False

        grid_size = max(self.model.grid.width, self.model.grid.height)
        timeout = max(1, (2 * grid_size) // 3)
        carry_since = self.carry_start_step.get(waste_type, self.model.steps)
        no_info_since = self.model.steps - self.last_waste_info_step.get(waste_type, -10**9)
        carried_for = self.model.steps - carry_since
        return carried_for >= timeout and no_info_since >= timeout

    def _post_action_bookkeeping(self):
        """Maintain carry timers and release communication lock when tasks finish."""
        for waste_type in ("green", "yellow", "red"):
            if self._inventory_count(waste_type) > 0 and waste_type not in self.carry_start_step:
                self.carry_start_step[waste_type] = self.model.steps
            if self._inventory_count(waste_type) == 0 and waste_type in self.carry_start_step:
                del self.carry_start_step[waste_type]

        if self.active_task is not None:
            task = self.active_task
            task_waste = task.get("waste_type")
            drop_target = self._task_drop_target(task.get("deliver_to"), task_waste)
            if self._inventory_count(task_waste) == 0 and self.pos == drop_target:
                self.active_task = None
                self.communication_locked = False

        if self.awaiting_assignment_until >= 0 and self.model.steps > self.awaiting_assignment_until and self.active_task is None:
            self.awaiting_assignment_until = -1

    def _border_drop_descriptor(self):
        if self.agent_role == "green" and self.pos[0] == self.model.z1[2] - 1:
            if self._inventory_count("green") > 0:
                return {"waste_type": "green", "next_role": "yellow"}

        if self.agent_role == "yellow" and self.pos[0] == self.model.z2[2] - 1:
            if self._inventory_count("green") > 0:
                return {"waste_type": "green", "next_role": "red"}
            if self._inventory_count("yellow") > 0:
                return {"waste_type": "yellow", "next_role": "red"}

        return None

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
        """Move toward nearest frontier, then fallback to safe random move."""
        frontier = []
        for pos in self.known_map:
            if not self.model.is_position_allowed(self, pos):
                continue
            for npos in neighbors_4(pos):
                if npos not in self.known_map and self.model.is_position_allowed(self, npos):
                    frontier.append(pos)
                    break
 
        if frontier:
            target = min(
                frontier,
                key=lambda p: manhattan(self.pos, p) + random.uniform(0, 0.5),
            )
            action = self._move_toward(target)
            if action:
                return action
 
        safe = self._safe_move_actions(self.percepts)
        if safe:
            return random.choice(safe)[0]
        return None

    def deliberate(self, knowledge=None):
        raise NotImplementedError("This method should be implemented by subclasses")

class greenAgent(baseAgent):
    """Green-zone robot focused on collecting green waste and producing yellow waste.

    Interacts with yellow agents at the zone border through asynchronous messages.
    """

    allowed_zones = ["z1"]
    target_waste_type = "green"
    result_waste_type = "yellow"
    max_capacity = 2
    agent_role = "green"

    def deliberate(self):
        priority_action = self._common_priority_action()
        if priority_action:
            return priority_action

        if self._inventory_count("green") >= 2:
            return "transform"

        if self._inventory_count("yellow") > 0:
            target_x = self.model.z1[2] - 1
            if self.pos[0] == target_x:
                if self.pending_query is None:
                    self._start_query(
                        role="yellow",
                        mode="carrying",
                        waste_type="yellow",
                        waste_pos=self.pos,
                        deliver_to="z2_east",
                        on_no_reply="broadcast_position",
                    )
                    send_action = self._send_next_message_action()
                    if send_action:
                        return send_action

                self._queue_message({
                    "to_role": "yellow",
                    "type": "waste_broadcast",
                    "payload": {
                        "pos": self.pos,
                        "waste_type": "yellow",
                        "deliver_to": "z2_east",
                    },
                })
                self._register_handover_request(self.pos, "yellow", "yellow", "z2_east")
                return "drop"

            target = (target_x, self.pos[1])
            action = self._move_toward(target)
            return action or self._explore_action()

        if self._inventory_count("green") > 0 and self._on_cell_has_waste("green") and len(self.inventory) < self.max_capacity:
            return "pick_up"

        if self._inventory_count("green") > 0 and self._carry_timeout_reached("green"):
            border_x = self.model.z1[2] - 1
            if self.pos[0] == border_x:
                if self.pending_query is None:
                    self._start_query(
                        role="yellow",
                        mode="free",
                        waste_type="green",
                        waste_pos=self.pos,
                        deliver_to="z2_east",
                        on_no_reply="broadcast_position",
                    )
                self._lock_border_waste(self.pos, "green", "yellow")
                self._register_handover_request(self.pos, "green", "yellow", "z2_east")
                return "drop"
            return self._move_toward((border_x, self.pos[1])) or self._explore_action()

        if self._on_cell_has_waste("green") and len(self.inventory) < self.max_capacity:
            if self._inventory_count("green") == 0 and self.pending_query is None:
                self._start_query(
                    role="green",
                    mode="carrying",
                    waste_type="green",
                    waste_pos=self.pos,
                    deliver_to="z1_east",
                    on_no_reply="pickup_if_here",
                )
                send_action = self._send_next_message_action()
                if send_action:
                    return send_action
            if self._inventory_count("green") > 0:
                return "pick_up"

        green_targets = self._known_targets("green")
        if green_targets:
            closest = min(green_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        return self._explore_action()

class yellowAgent(baseAgent):
    """Intermediate robot converting yellow waste to red and handling border handoffs.

    Coordinates upward with red agents and downward with green-border deliveries.
    """
 
    target_waste_type = "yellow"
    result_waste_type = "red"
    allowed_zones = ["z1", "z2"]
    max_capacity = 2
    agent_role = "yellow"
 
    def deliberate(self):
        priority_action = self._common_priority_action()
        if priority_action:
            return priority_action

        if self._inventory_count("yellow") >= 2:
            return "transform"

        if self._inventory_count("red") > 0:
            target_x = self.model.z2[2] - 1
            if self.pos[0] == target_x:
                if self.pending_query is None:
                    self._start_query(
                        role="red",
                        mode="free",
                        waste_type="red",
                        waste_pos=self.pos,
                        deliver_to="disposal",
                        on_no_reply="broadcast_position",
                    )
                return "drop"

            target = (target_x, self.pos[1])
            action = self._move_toward(target)
            return action or self._explore_action()

        if self._inventory_count("yellow") > 0 and self._carry_timeout_reached("yellow"):
            border_x = self.model.z2[2] - 1
            if self.pos[0] == border_x:
                self._queue_message({
                    "to_role": "red",
                    "type": "waste_broadcast",
                    "payload": {
                        "pos": self.pos,
                        "waste_type": "yellow",
                        "deliver_to": "disposal",
                    },
                })
                self._lock_border_waste(self.pos, "yellow", "red")
                self._register_handover_request(self.pos, "yellow", "red", "disposal")
                return "drop"
            return self._move_toward((border_x, self.pos[1])) or self._explore_action()

        if self._on_cell_has_waste("yellow") and len(self.inventory) < self.max_capacity:
                return "pick_up"

        yellow_targets = self._known_targets("yellow")
        if yellow_targets:
            closest = min(yellow_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        return self._explore_action()

class redAgent(baseAgent):
    """Final-stage robot that discovers disposal and evacuates red waste.

    Red agents can operate in all zones and finalize the waste disposal pipeline.
    """
 
    target_waste_type = "red"
    result_waste_type = None
    allowed_zones = ["z1", "z2", "z3"]
    max_capacity = 1
    agent_role = "red"

    def _detect_disposal_in_view(self):
        """Return disposal position if visible in current percept neighborhood."""
        surrounding = self.percepts.get("surrounding", {})
        for pos, contents in surrounding.items():
            for obj in contents:
                if hasattr(obj, "radioactivity") and obj.radioactivity == 10:
                    return pos
        return None
 
    def deliberate(self):
        priority_action = self._common_priority_action()
        if priority_action:
            return priority_action

        seen_disposal = self._detect_disposal_in_view()
        if seen_disposal is not None and self.disposal_pos_known is None:
            self.disposal_pos_known = seen_disposal
            self._queue_message({
                "to_role": "red",
                "type": "disposal_found",
                "payload": {"pos": seen_disposal},
            })
            send_action = self._send_next_message_action()
            if send_action:
                return send_action

        if self.disposal_pos_known is None:
            target_x = self.model.grid.width - 1
            if self.pos[0] < target_x:
                return self._move_toward((target_x, self.pos[1])) or self._explore_action()

            top = self.model.grid.height - 1
            if self.pos[1] == top:
                self.scan_direction = -1
            if self.pos[1] == 0:
                self.scan_direction = 1
            return "move_up" if self.scan_direction > 0 else "move_down"

        if self._inventory_count("red") > 0:
            if self._on_cell_has_waste("red") and self.pending_query is None:
                self._start_query(
                    role="red",
                    mode="free",
                    waste_type="red",
                    waste_pos=self.pos,
                    deliver_to="disposal",
                    on_no_reply="broadcast_position",
                )
                send_action = self._send_next_message_action()
                if send_action:
                    return send_action

            target = self.disposal_pos_known
            if self.pos == target:
                return "drop"
            action = self._move_toward(target)
            return action or self._explore_action()

        if self._on_cell_has_waste("red") and len(self.inventory) < self.max_capacity:
                return "pick_up"

        red_targets = self._known_targets("red")
        if red_targets:
            closest = min(red_targets, key=lambda p: manhattan(self.pos, p))
            if closest == self.pos:
                return "pick_up"
            action = self._move_toward(closest)
            return action or self._explore_action()

        return self._explore_action()