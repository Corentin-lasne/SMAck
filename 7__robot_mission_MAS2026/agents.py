""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent
import random
from config import actions
from objects import wasteAgent 

class baseAgent(Agent):
    def __init__(self, model):
        super().__init__(model)

        self.knowledge = {
            "observations": [],
            "actions": [],
        }
        self.target_waste = None
        self.percepts = self.model.get_percepts(self)
        self.inventory = []

    def step(self):
        self.step_agent()

    def step_agent(self):
        self.percepts = self.model.get_percepts(self)
        action = self.deliberate(self.knowledge)
        percepts = self.model.do(self, action)
        self.update(self.knowledge, percepts, action)

    def update(self, knowledge, percepts, action):
        knowledge["observations"].append(percepts)
        knowledge["actions"].append(action)

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
            occupied_by_robot = any(
                isinstance(obj, baseAgent) and obj is not self
                for obj in target_contents
            )
            if not occupied_by_robot:
                safe_actions.append(action_name)

        return safe_actions

    def deliberate(self, knowledge):
        # Au premier pas, aucune observation n'a encore été stockée.
        latest_observation = knowledge["observations"][-1] if knowledge["observations"] else self.percepts
        surrounding = latest_observation.get("surrounding", {})

        # Dans le cas où présence d'un déchêt dans l'entourage, on choisit de le ramasser
        if surrounding:
            for cell, contents in surrounding.items():
                for obj in contents:
                    # en fontion du type de déchêt et du type de l'agent il y a compatibilité ou non de ramassage, un agent vert ne peut ramasser que les déchets verts, un agent jaune peut ramasser les déchets verts et jaunes, un agent rouge peut ramasser tous les types de déchets
                    if isinstance(obj, wasteAgent):
                        if obj.waste_type == self.target_waste:
                            return "pick_up"

        non_move_actions = [action for action in actions.keys() if not action.startswith("move_")]
        safe_move_actions = self._safe_move_actions(latest_observation)
        available_actions = non_move_actions + safe_move_actions

        if not available_actions:
            return random.choice(non_move_actions)

        return random.choice(available_actions)

class greenAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1"]
        self.target_waste = "g"
        self.max_capacity = 2
    
class yellowAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1", "z2"]
        self.target_waste = "y"
        self.max_capacity = 2

class redAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1", "z2", "z3"]
        self.target_waste = "r"
        self.max_capacity = 1
