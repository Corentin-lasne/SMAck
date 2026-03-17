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

class baseAgent(Agent):
    def __init__(self, model):
        super().__init__(model)

        self.knowledge = {
            "observations": [],
            "actions": [],
        }

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

    @staticmethod
    def deliberate(knowledge):
        return random.choice(list(actions.keys()))


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
